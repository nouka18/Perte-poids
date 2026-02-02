import streamlit as st
from datetime import date, datetime
import csv
import os

# =========================
# Paramètres
# =========================
FICHIER_SUIVI = "poids_suivi.csv"

st.set_page_config(page_title="Perte de poids", page_icon="📉", layout="centered")
st.title("📉 Perte de poids : plan + suivi")
st.caption("Plan estimé (BMR/TDEE) + suivi quotidien avec moyenne 7 jours.")

# =========================
# Fonctions calcul plan
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
# Fonctions stockage CSV
# =========================
def charger_suivi():
    donnees = []
    if os.path.exists(FICHIER_SUIVI):
        with open(FICHIER_SUIVI, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                donnees.append({"date": row["date"], "poids": float(row["poids"])})
    donnees.sort(key=lambda x: x["date"])
    return donnees

def ecrire_suivi(donnees):
    with open(FICHIER_SUIVI, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "poids"])
        writer.writeheader()
        for d in donnees:
            writer.writerow(d)

def ajouter_ou_maj_mesure(date_str, poids):
    donnees = charger_suivi()
    found = False
    for d in donnees:
        if d["date"] == date_str:
            d["poids"] = poids
            found = True
            break
    if not found:
        donnees.append({"date": date_str, "poids": poids})
    donnees.sort(key=lambda x: x["date"])
    ecrire_suivi(donnees)

# =========================
# UI : Onglets (tel-friendly)
# =========================
tab_plan, tab_suivi = st.tabs(["🧮 Plan", "📅 Suivi quotidien"])

# -------------------------------------------------
# TAB 1 : PLAN
# -------------------------------------------------
with tab_plan:
    st.subheader("🧮 Calcul du plan (estimation)")

    col1, col2 = st.columns(2)
    with col1:
        poids = st.number_input("Poids actuel (kg)", 20.0, 300.0, 70.0, 0.1)
        taille_cm = st.number_input("Taille (cm)", 120.0, 230.0, 165.0, 1.0)
        age = st.number_input("Âge", 10, 120, 30, 1)
    with col2:
        sexe = st.selectbox("Sexe", ["Femme", "Homme"])
        activite = st.selectbox("Activité", ["Sédentaire", "Léger (1-3/sem)", "Modéré (3-5/sem)", "Élevé (6-7/sem)", "Très élevé"])
        objectif = st.number_input("Poids objectif (kg)", 20.0, 300.0, 62.0, 0.1)

    bmr = bmr_mifflin_st_jeor(poids, taille_cm, age, sexe)
    tdee = bmr * facteur_activite(activite)

    st.markdown("### 🎯 Déficit calorique")
    mode = st.radio("Choix", ["Auto (20%)", "Personnalisé"], horizontal=True)
    if mode == "Auto (20%)":
        deficit = max(300, min(0.20 * tdee, 800))
    else:
        deficit = st.slider("Déficit (kcal/j)", 200, 1000, 500, 50)

    calories_cible = tdee - deficit
    min_cal = 1200 if sexe == "Femme" else 1500
    if calories_cible < min_cal:
        calories_cible = min_cal
    deficit_reel = max(0.0, tdee - calories_cible)

    proteines_g = 1.6 * poids
    perte_totale = poids - objectif

    c1, c2, c3 = st.columns(3)
    c1.metric("BMR", f"{bmr:.0f} kcal/j")
    c2.metric("TDEE", f"{tdee:.0f} kcal/j")
    c3.metric("Cible", f"{calories_cible:.0f} kcal/j")

    st.write(f"**Déficit réel :** {deficit_reel:.0f} kcal/j")
    st.write(f"**Protéines (repère) :** {proteines_g:.0f} g/j")

    # Projection (courbe estimée)
    st.markdown("### 📉 Projection (estimation)")
    if perte_totale <= 0:
        st.info("Mets un poids objectif inférieur au poids actuel pour voir la projection.")
    elif deficit_reel <= 0:
        st.info("Déficit nul : augmente le déficit ou baisse la cible.")
    else:
        perte_par_semaine = (deficit_reel * 7) / 7700
        semaines_est = perte_totale / max(perte_par_semaine, 1e-6)

        # Limite raisonnable
        max_semaines = int(min(104, max(4, semaines_est + 2)))
        semaines = list(range(0, max_semaines + 1))
        poids_proj = [max(objectif, poids - perte_par_semaine * w) for w in semaines]

        st.line_chart({"Projection": poids_proj})
        st.success(f"Durée estimée ≈ **{semaines_est:.1f} semaines** (variable selon ton corps).")

# -------------------------------------------------
# TAB 2 : SUIVI QUOTIDIEN
# -------------------------------------------------
with tab_suivi:
    st.subheader("📅 Suivi quotidien")

    donnees = charger_suivi()

    colA, colB, colC = st.columns([1.2, 1.2, 1])
    with colA:
        d = st.date_input("Date", value=date.today())
    with colB:
        default_poids = donnees[-1]["poids"] if donnees else 70.0
        poids_jour = st.number_input("Poids du jour (kg)", 20.0, 300.0, float(default_poids), 0.1)
    with colC:
        st.write("")
        st.write("")
        if st.button("💾 Enregistrer"):
            ajouter_ou_maj_mesure(d.isoformat(), float(poids_jour))
            st.success("Mesure enregistrée ✅ (mise à jour si la date existait)")
            donnees = charger_suivi()

    if not donnees:
        st.info("Ajoute une première mesure pour afficher la courbe.")
    else:
        # séries
        dates = [datetime.fromisoformat(x["date"]).date() for x in donnees]
        poids_vals = [x["poids"] for x in donnees]
        ma7 = moyenne_glissante(poids_vals, window=7)

        st.markdown("### 📈 Courbe (jour + moyenne 7 jours)")
        st.line_chart({"Poids": poids_vals, "Moyenne 7 jours": ma7})

        st.markdown("### 📌 Indicateurs")
        st.write(f"- **Dernier poids** : {poids_vals[-1]:.1f} kg")
        st.write(f"- **Depuis le début** : {poids_vals[-1] - poids_vals[0]:+.1f} kg")
        if len(ma7) >= 7:
            st.write(f"- **Moyenne 7 jours actuelle** : {ma7[-1]:.1f} kg")

        st.markdown("### 📋 Historique")
        st.dataframe(donnees, use_container_width=True)

        # Export
        with open(FICHIER_SUIVI, "rb") as f:
            st.download_button("⬇️ Télécharger CSV", data=f, file_name="poids_suivi.csv", mime="text/csv")

        # Reset
        if st.button("🗑️ Réinitialiser l'historique"):
            if os.path.exists(FICHIER_SUIVI):
                os.remove(FICHIER_SUIVI)
            st.warning("Historique supprimé. Recharge la page.")
