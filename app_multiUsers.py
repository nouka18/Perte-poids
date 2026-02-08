import streamlit as st
from datetime import date, datetime
import pandas as pd
import altair as alt
import gspread
from google.oauth2.service_account import Credentials

# =========================
# Secrets check
# =========================
st.set_page_config(page_title="Perte de poids", page_icon="📉", layout="centered")

if (
    "gcp_service_account" not in st.secrets
    or "app" not in st.secrets
    or "spreadsheet_id" not in st.secrets["app"]
):
    st.error("Secrets manquants : ajoute [gcp_service_account] et [app].spreadsheet_id dans Streamlit → Secrets.")
    st.stop()

# =========================
# Google Sheets (cache)
# =========================
@st.cache_resource
def get_gs_client():
    creds_info = st.secrets["gcp_service_account"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def get_spreadsheet():
    gc = get_gs_client()
    return gc.open_by_key(st.secrets["app"]["spreadsheet_id"])

@st.cache_resource
def get_worksheets_cached():
    sh = get_spreadsheet()
    ws_profil = sh.worksheet("profil")
    ws_poids = sh.worksheet("poids")
    return ws_profil, ws_poids

def get_worksheets():
    return get_worksheets_cached()

# =========================
# Defaults profil
# =========================
DEFAULT_PROFIL = {
    "poids_actuel": "70.0",
    "taille_cm": "165.0",
    "age": "30",
    "sexe": "Femme",
    "objectif": "62.0",
    "mode_deficit": "Auto (20%)",
    "deficit_perso": "500",
    "niveau_job": "Faible (1.5)",
    "intensite_sport": "Moyenne (0.04 × h/sem)",
    "heures_sport": "3.0",
}

# =========================
# Helpers PAb + PAs + BMR
# =========================
def bmr_mifflin_st_jeor(poids_kg, taille_cm, age, sexe):
    base = 10 * poids_kg + 6.25 * taille_cm - 5 * age
    return base + 5 if sexe == "Homme" else base - 161

def pAb_from_job(niveau_job: str) -> float:
    return {
        "Très faible (1.4)": 1.4,
        "Faible (1.5)": 1.5,
        "Modéré (1.6)": 1.6,
        "Important (1.7)": 1.7,
    }[niveau_job]

def pAs_from_sport(intensite: str, heures_par_semaine: float) -> float:
    coeff = {
        "Faible (0.02 × h/sem)": 0.02,
        "Moyenne (0.04 × h/sem)": 0.04,
        "Forte (0.06 × h/sem)": 0.06,
    }[intensite]
    return coeff * heures_par_semaine

def moyenne_glissante(values, window=7):
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start:i + 1]
        out.append(sum(chunk) / len(chunk))
    return out

# =========================
# PROFIL (multi-user)
# profil sheet headers: user_id | key | value
# =========================
@st.cache_data(ttl=60)
def profil_lire_user_cached(user_id: str) -> dict:
    ws_profil, _ = get_worksheets()
    rows = ws_profil.get_all_values()
    if not rows:
        return DEFAULT_PROFIL.copy()

    # Expect headers
    # rows[0] = ["user_id","key","value"]
    data = {}
    for r in rows[1:]:
        if len(r) >= 3 and r[0] == user_id:
            data[r[1]] = r[2]

    # fill defaults
    for k, v in DEFAULT_PROFIL.items():
        data.setdefault(k, v)
    return data

def profil_lire_user(user_id: str) -> dict:
    return profil_lire_user_cached(user_id)

def profil_upsert_user(user_id: str, data: dict):
    ws_profil, _ = get_worksheets()
    rows = ws_profil.get_all_values()

    # Ensure header
    if len(rows) == 0:
        ws_profil.append_row(["user_id", "key", "value"])
        rows = ws_profil.get_all_values()

    # Build index map (user_id,key) -> row number in sheet (1-based)
    index = {}
    for i, r in enumerate(rows[1:], start=2):
        if len(r) >= 3:
            index[(r[0], r[1])] = i

    # Upsert each key (few keys => acceptable)
    for k, v in data.items():
        key = (user_id, k)
        if key in index:
            rownum = index[key]
            ws_profil.update(f"C{rownum}", str(v))
        else:
            ws_profil.append_row([user_id, k, str(v)])

    profil_lire_user_cached.clear()

# =========================
# POIDS (multi-user)
# poids sheet headers: user_id | date | poids
# =========================
@st.cache_data(ttl=30)
def poids_lire_user_df_cached(user_id: str) -> pd.DataFrame:
    _, ws_poids = get_worksheets()
    rows = ws_poids.get_all_values()
    if len(rows) <= 1:
        return pd.DataFrame(columns=["date", "poids"])

    df = pd.DataFrame(rows[1:], columns=rows[0])
    # Filter user
    df = df[df["user_id"] == user_id].copy()
    if df.empty:
        return pd.DataFrame(columns=["date", "poids"])

    df["poids"] = pd.to_numeric(df["poids"], errors="coerce")
    df = df.dropna(subset=["poids"]).sort_values("date")
    return df[["date", "poids"]]

def poids_lire_user_df(user_id: str) -> pd.DataFrame:
    return poids_lire_user_df_cached(user_id)

def poids_ajouter_ou_maj_user(user_id: str, date_iso: str, poids: float):
    _, ws_poids = get_worksheets()
    rows = ws_poids.get_all_values()

    # Ensure header
    if len(rows) == 0:
        ws_poids.append_row(["user_id", "date", "poids"])
        rows = ws_poids.get_all_values()

    # Search existing row for (user_id, date)
    for idx, r in enumerate(rows[1:], start=2):
        if len(r) >= 3 and r[0] == user_id and r[1] == date_iso:
            ws_poids.update(f"C{idx}", str(poids))
            poids_lire_user_df_cached.clear()
            return

    ws_poids.append_row([user_id, date_iso, str(poids)])
    poids_lire_user_df_cached.clear()

# =========================
# UI
# =========================
st.title("📉 Perte de poids : plan + suivi (multi-utilisateur)")
st.caption("Chaque utilisateur a son profil + son historique séparés via un identifiant (user_id).")

user_id = st.text_input(
    "Ton identifiant (user_id) — ex: nouha ou ton email",
    value=st.session_state.get("user_id", "")
).strip().lower()

if not user_id:
    st.info("Entre un identifiant pour charger tes données.")
    st.stop()

st.session_state["user_id"] = user_id

tab_plan, tab_suivi = st.tabs(["🧮 Plan", "📅 Suivi quotidien"])

# Load profil for this user
profil = profil_lire_user(user_id)

# =========================
# TAB PLAN
# =========================
with tab_plan:
    st.subheader("🧮 Plan (estimation)")

    col1, col2 = st.columns(2)
    with col1:
        poids_actuel = st.number_input("Poids actuel (kg)", 20.0, 300.0, float(profil["poids_actuel"]), 0.1)
        taille_cm = st.number_input("Taille (cm)", 120.0, 230.0, float(profil["taille_cm"]), 1.0)
        age = st.number_input("Âge", 10, 120, int(float(profil["age"])), 1)
    with col2:
        sexe = st.selectbox("Sexe", ["Femme", "Homme"], index=0 if profil["sexe"] == "Femme" else 1)
        objectif = st.number_input("Poids objectif (kg)", 20.0, 300.0, float(profil["objectif"]), 0.1)

    # ---- PAb + PAs (avec explications) ----
    st.markdown("## 🏃 Facteur d’activité (PA = PAb + PAs)")
    st.caption("PAb = activité au travail (hors sport). PAs = sport en heures/semaine.")

    st.markdown("### 🧑‍💼 Activité professionnelle (PAb)")
    job_options = ["Très faible (1.4)", "Faible (1.5)", "Modéré (1.6)", "Important (1.7)"]
    job_default = profil.get("niveau_job", "Faible (1.5)")
    job_index = job_options.index(job_default) if job_default in job_options else 1
    niveau_job = st.selectbox("Choisis ton niveau au travail (hors sport)", job_options, index=job_index)

    desc_job = {
        "Très faible (1.4)": "💺 Travail assis. Ex: bureau, développeur, comptable, chauffeur.",
        "Faible (1.5)": "🚶‍♀️ Debout / déplacements légers. Ex: enseignant, vendeur, coiffeur.",
        "Modéré (1.6)": "💪 Actif physiquement. Ex: serveur, ménage, aide-soignant, kiné.",
        "Important (1.7)": "🏋️ Très physique. Ex: bâtiment, déménagement, agriculture.",
    }
    st.info(desc_job[niveau_job])
    pAb = pAb_from_job(niveau_job)

    st.markdown("### 🏃 Activité sportive (PAs)")
    sport_options = ["Faible (0.02 × h/sem)", "Moyenne (0.04 × h/sem)", "Forte (0.06 × h/sem)"]
    sport_default = profil.get("intensite_sport", "Moyenne (0.04 × h/sem)")
    sport_index = sport_options.index(sport_default) if sport_default in sport_options else 1
    intensite_sport = st.selectbox("Intensité du sport", sport_options, index=sport_index)

    desc_sport = {
        "Faible (0.02 × h/sem)": "🧘 Yoga, stretching, marche lente.",
        "Moyenne (0.04 × h/sem)": "🚴 Marche rapide, vélo, natation tranquille.",
        "Forte (0.06 × h/sem)": "🏃 Jogging, HIIT, cross-training, squash.",
    }
    st.caption(desc_sport[intensite_sport])

    heures_default = float(profil.get("heures_sport", "3.0") or 3.0)
    heures_sport = st.number_input("Heures de sport / semaine", 0.0, 40.0, float(heures_default), 0.5)

    pAs = pAs_from_sport(intensite_sport, heures_sport)
    PA = pAb + pAs

    st.success(f"**PAb = {pAb:.2f}** | **PAs = {pAs:.2f}** → **PA total = {PA:.2f}**")
    if PA < 1.4 or PA > 1.8:
        st.warning("⚠️ PA hors plage 1.4–1.8 (selon la source). Vérifie job/heures.")

    # ---- BMR/TDEE + déficit ----
    bmr = bmr_mifflin_st_jeor(poids_actuel, taille_cm, age, sexe)
    tdee = bmr * PA

    st.markdown("### 🎯 Déficit calorique")
    mode_opts = ["Auto (20%)", "Personnalisé"]
    mode_deficit = st.radio(
        "Choix", mode_opts, horizontal=True,
        index=0 if profil.get("mode_deficit", "Auto (20%)") == "Auto (20%)" else 1
    )

    if mode_deficit == "Auto (20%)":
        deficit = max(300.0, min(0.20 * tdee, 800.0))
        deficit_perso = float(profil.get("deficit_perso", "500"))
    else:
        deficit_perso = float(st.slider("Déficit (kcal/j)", 200, 1000, int(float(profil.get("deficit_perso", "500"))), 50))
        deficit = deficit_perso

    calories_cible = tdee - deficit
    min_cal = 1200.0 if sexe == "Femme" else 1500.0
    if calories_cible < min_cal:
        calories_cible = min_cal
    deficit_reel = max(0.0, tdee - calories_cible)

    proteines_g = 1.6 * poids_actuel
    perte_totale = poids_actuel - objectif

    c1, c2, c3 = st.columns(3)
    c1.metric("BMR", f"{bmr:.0f} kcal/j")
    c2.metric("TDEE", f"{tdee:.0f} kcal/j")
    c3.metric("Cible", f"{calories_cible:.0f} kcal/j")

    st.write(f"**Déficit réel :** {deficit_reel:.0f} kcal/j")
    st.write(f"**Protéines (repère) :** {proteines_g:.0f} g/j")

    # Save for follow-up chart
    st.session_state["plan_poids_depart"] = float(poids_actuel)
    st.session_state["plan_objectif"] = float(objectif)
    st.session_state["plan_deficit_reel"] = float(deficit_reel)

    # ---- Save profil (for this user) ----
    st.markdown("### 💾 Sauvegarde profil")
    if st.button("Sauvegarder mon profil"):
        nouveau = {
            "poids_actuel": poids_actuel,
            "taille_cm": taille_cm,
            "age": age,
            "sexe": sexe,
            "objectif": objectif,
            "mode_deficit": mode_deficit,
            "deficit_perso": deficit_perso,
            "niveau_job": niveau_job,
            "intensite_sport": intensite_sport,
            "heures_sport": heures_sport,
        }
        profil_upsert_user(user_id, nouveau)
        st.success("Profil sauvegardé ✅")
        profil = profil_lire_user(user_id)

    # ---- Projection ----
    st.markdown("### 📉 Projection (estimation)")
    if perte_totale <= 0:
        st.info("Mets un objectif inférieur au poids actuel pour voir la projection.")
    elif deficit_reel <= 0:
        st.info("Déficit nul : augmente le déficit ou baisse la cible.")
    else:
        perte_par_semaine = (deficit_reel * 7) / 7700.0
        semaines_est = perte_totale / max(perte_par_semaine, 1e-6)
        max_semaines = int(min(104, max(4, semaines_est + 2)))
        semaines = list(range(0, max_semaines + 1))
        poids_proj = [max(objectif, poids_actuel - perte_par_semaine * w) for w in semaines]
        st.line_chart(pd.DataFrame({"Projection": poids_proj}, index=semaines))
        st.success(f"Durée estimée ≈ **{semaines_est:.1f} semaines**")

# =========================
# TAB SUIVI
# =========================
with tab_suivi:
    st.subheader("📅 Suivi quotidien")

    df = poids_lire_user_df(user_id)

    colA, colB, colC = st.columns([1.2, 1.2, 1])
    with colA:
        d = st.date_input("Date", value=date.today())
    with colB:
        last = float(df["poids"].iloc[-1]) if len(df) else float(profil.get("poids_actuel", "70.0"))
        poids_jour = st.number_input("Poids du jour (kg)", 20.0, 300.0, last, 0.1)
    with colC:
        st.write("")
        st.write("")
        if st.button("💾 Enregistrer la mesure"):
            poids_ajouter_ou_maj_user(user_id, d.isoformat(), float(poids_jour))
            st.success("Mesure enregistrée ✅")
            df = poids_lire_user_df(user_id)

    st.divider()

    if df.empty:
        st.info("Ajoute une première mesure pour afficher le graphe.")
        st.stop()

    # Weeks since first measurement
    dates_dt = [datetime.fromisoformat(x) for x in df["date"].astype(str).tolist()]
    t0 = dates_dt[0]
    semaines_reel = [((dt - t0).days / 7.0) for dt in dates_dt]

    poids_vals = df["poids"].tolist()
    ma7 = moyenne_glissante(poids_vals, window=7)

    df_reel = pd.DataFrame({"semaine": semaines_reel, "poids": poids_vals, "serie": "Réel"})
    df_ma7 = pd.DataFrame({"semaine": semaines_reel, "poids": ma7, "serie": "Moyenne 7 jours"})

    # Projection from plan (if computed this session)
    df_proj = pd.DataFrame(columns=["semaine", "poids", "serie"])
    poids_depart_plan = st.session_state.get("plan_poids_depart")
    objectif = st.session_state.get("plan_objectif")
    deficit_reel = st.session_state.get("plan_deficit_reel")

    if poids_depart_plan is not None and objectif is not None and deficit_reel is not None:
        if (poids_depart_plan - objectif) > 0 and deficit_reel > 0:
            perte_par_semaine = (deficit_reel * 7) / 7700.0
            semaines_max = int(min(104, max(4, (poids_depart_plan - objectif) / max(perte_par_semaine, 1e-6) + 2)))
            semaines = list(range(0, semaines_max + 1))
            poids_proj = [max(objectif, poids_depart_plan - perte_par_semaine * w) for w in semaines]
            df_proj = pd.DataFrame({"semaine": semaines, "poids": poids_proj, "serie": "Projection"})

    df_all = pd.concat([df_proj, df_reel, df_ma7], ignore_index=True)

    st.markdown("### 📈 Réel vs Projection (axe semaines)")
    base = alt.Chart(df_all).encode(
        x=alt.X("semaine:Q", title="Semaines depuis la 1ère mesure"),
        y=alt.Y("poids:Q", title="Poids (kg)")
    )

    lignes = base.transform_filter(
        alt.FieldOneOfPredicate(field="serie", oneOf=["Projection", "Moyenne 7 jours"])
    ).mark_line().encode(color="serie:N")

    points = base.transform_filter(
        alt.datum.serie == "Réel"
    ).mark_circle(size=70).encode(color="serie:N")

    st.altair_chart((lignes + points).interactive(), use_container_width=True)

    st.markdown("### 📌 Indicateurs")
    st.write(f"- **Dernier poids** : {poids_vals[-1]:.1f} kg")
    st.write(f"- **Depuis le début** : {poids_vals[-1] - poids_vals[0]:+.1f} kg")
    if len(ma7) >= 7:
        st.write(f"- **Moyenne 7 jours actuelle** : {ma7[-1]:.1f} kg")

    st.markdown("### 📋 Historique (toi uniquement)")
    st.dataframe(df, use_container_width=True)
