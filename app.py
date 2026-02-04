import streamlit as st
from datetime import date, datetime
import pandas as pd
import altair as alt
import gspread
from google.oauth2.service_account import Credentials

# =========================
# Connexion Google Sheets
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

def get_worksheets():
    gc = get_gs_client()
    sh = gc.open_by_key(st.secrets["app"]["spreadsheet_id"])
    ws_profil = sh.worksheet("profil")
    ws_poids = sh.worksheet("poids")
    return ws_profil, ws_poids

# =========================
# Fonctions Profil
# =========================
DEFAULT_PROFIL = {
    "poids_actuel": "70.0",
    "taille_cm": "165.0",
    "age": "30",
    "sexe": "Femme",
    "activite": "Modéré (3-5/sem)",
    "objectif": "62.0",
    "mode_deficit": "Auto (20%)",
    "deficit_perso": "500",
}

def profil_lire():
    ws_profil, _ = get_worksheets()
    rows = ws_profil.get_all_values()
    # rows[0] = headers ["key","value"]
    data = {}
    for r in rows[1:]:
        if len(r) >= 2:
            data[r[0]] = r[1]
    # compléter par défaut
    for k, v in DEFAULT_PROFIL.items():
        data.setdefault(k, v)
    return data

def profil_ecrire(data: dict):
    ws_profil, _ = get_worksheets()
    # on réécrit tout proprement
    ws_profil.clear()
    ws_profil.append_row(["key", "value"])
    for k, v in data.items():
        ws_profil.append_row([k, str(v)])

# =========================
# Fonctions Poids quotidien
# =========================
def poids_lire_df():
    _, ws_poids = get_worksheets()
    rows = ws_poids.get_all_values()
    if len(rows) <= 1:
        return pd.DataFrame(columns=["date", "poids"])
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df["poids"] = pd.to_numeric(df["poids"], errors="coerce")
    df = df.dropna(subset=["poids"])
    df = df.sort_values("date")
    return df

def poids_ajouter_ou_maj(date_iso: str, poids: float):
    _, ws_poids = get_worksheets()
    rows = ws_poids.get_all_values()

    # si sheet vide -> écrire headers
    if len(rows) == 0:
        ws_poids.append_row(["date", "poids"])
        rows = ws_poids.get_all_values()

    # si juste headers -> ajouter
    if len(rows) == 1:
        ws_poids.append_row([date_iso, str(poids)])
        return

    # chercher date existante
    # rows: [ ["date","poids"], ["2026-02-01","70.2"], ... ]
    for idx, r in enumerate(rows[1:], start=2):  # index gspread commence à 1
        if len(r) >= 1 and r[0] == date_iso:
            ws_poids.update(f"B{idx}", str(poids))  # colonne B
            return

    # sinon append
    ws_poids.append_row([date_iso, str(poids)])

# =========================
# Plan (BMR/TDEE)
# =========================
def bmr_mifflin_st_jeor(poids_kg, taille_cm, age, sexe):
    base = 10 * poids_kg + 6.25 * taille_cm - 5 * age
    return base + 5 if sexe == "Homme" else base - 161

def facteur_activite(niveau):
    return {
        "Sédentaire": 1.2,
        "Léger (1-3/sem)": 1.375,
        "Modéré (3-5/sem)": 1.55,
        "Élevé (6-7/sem)": 1.725,
        "Très élevé": 1.9
    }[niveau]

def moyenne_glissante(values, window=7):
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start:i+1]
        out.append(sum(chunk) / len(chunk))
    return out

# =========================
# UI
# =========================
st.set_page_config(page_title="Perte de poids", page_icon="📉", layout="centered")
st.title("📉 Perte de poids : plan + suivi")
st.caption("Données sauvegardées dans Google Sheets (profil + poids quotidien).")

tab_plan, tab_suivi = st.tabs(["🧮 Plan", "📅 Suivi quotidien"])

# Charger profil au démarrage
profil = profil_lire()

# -------------------------------------------------
# TAB PLAN
# -------------------------------------------------
with tab_plan:
    st.subheader("🧮 Plan (estimation)")

    col1, col2 = st.columns(2)
    with col1:
        poids_actuel = st.number_input("Poids actuel (kg)", 20.0, 300.0, float(profil["poids_actuel"]), 0.1)
        taille_cm = st.number_input("Taille (cm)", 120.0, 230.0, float(profil["taille_cm"]), 1.0)
        age = st.number_input("Âge", 10, 120, int(float(profil["age"])), 1)
    with col2:
        sexe = st.selectbox("Sexe", ["Femme", "Homme"], index=0 if profil["sexe"] == "Femme" else 1)
        activite_opts = ["Sédentaire", "Léger (1-3/sem)", "Modéré (3-5/sem)", "Élevé (6-7/sem)", "Très élevé"]
        activite = st.selectbox("Activité", activite_opts, index=activite_opts.index(profil["activite"]) if profil["activite"] in activite_opts else 2)
        objectif = st.number_input("Poids objectif (kg)", 20.0, 300.0, float(profil["objectif"]), 0.1)

    bmr = bmr_mifflin_st_jeor(poids_actuel, taille_cm, age, sexe)
    tdee = bmr * facteur_activite(activite)

    st.markdown("### 🎯 Déficit calorique")
    mode_opts = ["Auto (20%)", "Personnalisé"]
    mode_deficit = st.radio("Choix", mode_opts, horizontal=True, index=0 if profil["mode_deficit"] == "Auto (20%)" else 1)

    if mode_deficit == "Auto (20%)":
        deficit = max(300.0, min(0.20 * tdee, 800.0))
        deficit_perso = float(profil["deficit_perso"])
    else:
        deficit_perso = float(st.slider("Déficit (kcal/j)", 200, 1000, int(float(profil["deficit_perso"])), 50))
        deficit = float(deficit_perso)

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

    st.markdown("### 💾 Profil")
    if st.button("Sauvegarder mon profil"):
        nouveau = {
            "poids_actuel": poids_actuel,
            "taille_cm": taille_cm,
            "age": age,
            "sexe": sexe,
            "activite": activite,
            "objectif": objectif,
            "mode_deficit": mode_deficit,
            "deficit_perso": deficit_perso,
        }
        profil_ecrire(nouveau)
        st.success("Profil sauvegardé dans Google Sheets ✅")

    st.markdown("### 📉 Projection (estimation)")
    if perte_totale <= 0:
        st.info("Mets un poids objectif inférieur au poids actuel pour voir la projection.")
    elif deficit_reel <= 0:
        st.info("Déficit nul : augmente le déficit ou baisse la cible.")
    else:
        perte_par_semaine = (deficit_reel * 7) / 7700.0
        semaines_est = perte_totale / max(perte_par_semaine, 1e-6)
        max_semaines = int(min(104, max(4, semaines_est + 2)))
        semaines = list(range(0, max_semaines + 1))
        poids_proj = [max(objectif, poids_actuel - perte_par_semaine * w) for w in semaines]
        st.line_chart(pd.DataFrame({"Projection": poids_proj}, index=semaines))
        st.success(f"Durée estimée ≈ **{semaines_est:.1f} semaines** (variable selon ton corps).")

    # Stocker en session pour l'onglet suivi (projection)
    st.session_state["plan_poids_depart"] = float(poids_actuel)
    st.session_state["plan_objectif"] = float(objectif)
    st.session_state["plan_deficit_reel"] = float(deficit_reel)

# -------------------------------------------------
# TAB SUIVI
# -------------------------------------------------
with tab_suivi:
    st.subheader("📅 Suivi quotidien (Google Sheets)")

    df = poids_lire_df()

    colA, colB, colC = st.columns([1.2, 1.2, 1])
    with colA:
        d = st.date_input("Date", value=date.today())
    with colB:
        last = float(df["poids"].iloc[-1]) if len(df) else float(profil["poids_actuel"])
        poids_jour = st.number_input("Poids du jour (kg)", 20.0, 300.0, last, 0.1)
    with colC:
        st.write("")
        st.write("")
        if st.button("💾 Enregistrer la mesure"):
            poids_ajouter_ou_maj(d.isoformat(), float(poids_jour))
            st.success("Mesure enregistrée ✅")
            df = poids_lire_df()

    st.divider()

    if df.empty:
        st.info("Ajoute une première mesure pour afficher le graphe.")
    else:
        # semaines depuis 1ère mesure
        dates_dt = [datetime.fromisoformat(x) for x in df["date"].astype(str).tolist()]
        t0 = dates_dt[0]
        semaines_reel = [((dt - t0).days / 7.0) for dt in dates_dt]

        poids_vals = df["poids"].tolist()
        ma7 = moyenne_glissante(poids_vals, window=7)

        df_reel = pd.DataFrame({"semaine": semaines_reel, "poids": poids_vals, "serie": "Réel"})
        df_ma7 = pd.DataFrame({"semaine": semaines_reel, "poids": ma7, "serie": "Moyenne 7 jours"})

        # projection (si plan déjà calculé)
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

        st.markdown("### 📋 Historique")
        st.dataframe(df, use_container_width=True)
