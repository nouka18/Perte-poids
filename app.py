import streamlit as st
import matplotlib.pyplot as plt
from datetime import date
import csv
import os

# ---------- Calculs ----------
def bmr_mifflin_st_jeor(poids_kg, taille_cm, age, sexe):
    base = 10 * poids_kg + 6.25 * taille_cm - 5 * age
    return base + 5 if sexe == "Homme" else base - 161

def facteur_activite(niveau):
    return {
        "Sédentaire (peu/pas de sport)": 1.2,
        "Léger (1-3 séances/sem)": 1.375,
        "Modéré (3-5 séances/sem)": 1.55,
        "Élevé (6-7 séances/sem)": 1.725,
        "Très élevé (travail physique + sport)": 1.9
    }[niveau]

# ---------- Stockage ----------
FICHIER_SUIVI = "poids_suivi.csv"

def charger_suivi():
    donnees = []
    if os.path.exists(FICHIER_SUIVI):
        with open(FICHIER_SUIVI, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                donnees.append({"date": row["date"], "poids": float(row["poids"])})
    return donnees

def ajouter_mesure(date_str, poids):
    existe = os.path.exists(FICHIER_SUIVI)
    with open(FICHIER_SUIVI, "a", newline="", encoding="utf-8") as f:
        champs = ["date", "poids"]
        writer = csv.DictWriter(f, fieldnames=champs)
        if not existe:
            writer.writeheader()
        writer.writerow({"date": date_str, "poids": poids})

# ---------- UI ----------
st.set_page_config(page_title="Plan Perte de Poids", page_icon="📉", layout="centered")
st.title("📉 Plan + Suivi Perte de Poids")
st.caption("Estimation BMR/TDEE + suivi hebdomadaire (CSV).")

# ---- Inputs principaux ----
col1, col2 = st.columns(2)
with col1:
    poids = st.number_input("Poids actuel (kg)", min_value=20.0, max_value=300.0, value=70.0, step=0.1)
    taille_cm = st.number_input("Taille (cm)", min_value=120.0, max_value=230.0, value=165.0, step=1.0)
    age = st.number_input("Âge (ans)", min_value=10, max_value=120, value=30, step=1)
with col2:
    sexe = st.selectbox("Sexe", ["Femme", "Homme"])
    activite = st.selectbox(
        "Niveau d'activité",
        [
            "Sédentaire (peu/pas de sport)",
            "Léger (1-3 séances/sem)",
            "Modéré (3-5 séances/sem)",
            "Élevé (6-7 séances/sem)",
            "Très élevé (travail physique + sport)"
        ]
    )
    objectif = st.number_input("Poids objectif (kg)", min_value=20.0, max_value=300.0, value=62.0, step=0.1)

st.divider()

# ---- Calculs calories ----
bmr = bmr_mifflin_st_jeor(poids, taille_cm, age, sexe)
tdee = bmr * facteur_activite(activite)

st.subheader("🎯 Déficit calorique")
mode = st.radio("Mode", ["Auto (20%)", "Personnalisé"], horizontal=True)
if mode == "Auto (20%)":
    deficit = max(300, min(0.20 * tdee, 800))
else:
    deficit = st.slider("Déficit (kcal/j)", 200, 1000, 500, 50)

calories_cible = tdee - deficit
# mini garde-fou très simple
min_cal = 1200 if sexe == "Femme" else 1500
if calories_cible < min_cal:
    calories_cible = min_cal
deficit_reel = max(0, tdee - calories_cible)

perte_totale = poids - objectif
proteines_g = 1.6 * poids

c1, c2, c3 = st.columns(3)
c1.metric("BMR", f"{bmr:.0f} kcal/j")
c2.metric("TDEE", f"{tdee:.0f} kcal/j")
c3.metric("Cible", f"{calories_cible:.0f} kcal/j")

st.write(f"**Déficit réel :** {deficit_reel:.0f} kcal/j")
st.write(f"**Protéines (repère) :** {proteines_g:.0f} g/j")

st.divider()

# ---- Projection ----
st.subheader("📈 Graphe : projection vs suivi réel")

# projection en semaines
semaines = []
poids_proj = []
if perte_totale > 0 and deficit_reel > 0:
    perte_par_semaine = (deficit_reel * 7) / 7700
    semaines_max = int(min(104, max(2, (perte_totale / max(perte_par_semaine, 1e-6)) + 2)))
    semaines = list(range(0, semaines_max + 1))
    for w in semaines:
        p = poids - perte_par_semaine * w
        poids_proj.append(max(objectif, p))

# ---- Suivi réel (CSV) ----
st.markdown("### ✅ Suivi hebdomadaire (à remplir)")
donnees = charger_suivi()

colA, colB, colC = st.columns([1.2, 1.2, 1])
with colA:
    d = st.date_input("Date de mesure", value=date.today())
with colB:
    poids_mesure = st.number_input("Poids mesuré (kg)", min_value=20.0, max_value=300.0, value=float(poids), step=0.1)
with colC:
    st.write("")
    st.write("")
    if st.button("➕ Ajouter"):
        ajouter_mesure(d.isoformat(), poids_mesure)
        st.success("Mesure ajoutée ✅ (enregistrée dans poids_suivi.csv)")
        donnees = charger_suivi()

# points réels
dates = [x["date"] for x in donnees]
poids_reel = [x["poids"] for x in donnees]

# ---- Graphe ----
fig, ax = plt.subplots()

if semaines:
    ax.plot(semaines, poids_proj, label="Projection")

if dates:
    # On met les mesures réelles sur l’axe x en index (0,1,2...) = semaines/mesures
    # Simple et robuste sans parsing calendrier
    x_reel = list(range(len(poids_reel)))
    ax.plot(x_reel, poids_reel, marker="o", linestyle="-", label="Réel (mesures)")
    ax.set_xlabel("Semaines / Mesures")
else:
    ax.set_xlabel("Semaines")

ax.set_ylabel("Poids (kg)")
ax.grid(True)
ax.legend()
st.pyplot(fig)

# ---- Affichage tableau suivi ----
if donnees:
    st.markdown("### 📋 Historique")
    st.dataframe(donnees, use_container_width=True)

    if st.button("🗑️ Réinitialiser l'historique"):
        if os.path.exists(FICHIER_SUIVI):
            os.remove(FICHIER_SUIVI)
        st.warning("Historique supprimé. Relance l’app ou ajoute une nouvelle mesure.")
else:
    st.info("Ajoute ta première mesure pour commencer le suivi.")
