import streamlit as st
import matplotlib.pyplot as plt
from datetime import date, datetime
import csv
import os

FICHIER_SUIVI = "poids_suivi.csv"

# ---------- Utils CSV ----------
def charger_suivi():
    donnees = []
    if os.path.exists(FICHIER_SUIVI):
        with open(FICHIER_SUIVI, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                donnees.append({
                    "date": row["date"],
                    "poids": float(row["poids"])
                })
    # tri par date
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
    # si une entrée existe déjà pour la date -> MAJ
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

def moyenne_glissante(values, window=7):
    # simple moving average (SMA)
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start:i+1]
        out.append(sum(chunk) / len(chunk))
    return out

# ---------- UI ----------
st.set_page_config(page_title="Suivi poids quotidien", page_icon="📉", layout="centered")
st.title("📉 Suivi du poids (quotidien)")
st.caption("Entre ton poids chaque jour. L’app calcule une moyenne glissante 7 jours (plus stable).")

donnees = charger_suivi()

st.subheader("➕ Ajouter / mettre à jour une mesure")
col1, col2, col3 = st.columns([1.2, 1.2, 1])

with col1:
    d = st.date_input("Date", value=date.today())
with col2:
    default_poids = donnees[-1]["poids"] if donnees else 70.0
    poids = st.number_input("Poids (kg)", min_value=20.0, max_value=300.0, value=float(default_poids), step=0.1)
with col3:
    st.write("")
    st.write("")
    if st.button("💾 Enregistrer"):
        ajouter_ou_maj_mesure(d.isoformat(), float(poids))
        st.success("Mesure enregistrée ✅ (ou mise à jour si la date existait)")
        donnees = charger_suivi()

st.divider()

# ---------- Graphe ----------
st.subheader("📈 Courbe (brut + moyenne 7 jours)")

if donnees:
    dates = [datetime.fromisoformat(x["date"]) for x in donnees]
    poids_vals = [x["poids"] for x in donnees]
    ma7 = moyenne_glissante(poids_vals, window=7)

    fig, ax = plt.subplots()
    ax.plot(dates, poids_vals, marker="o", linestyle="-", label="Poids (jour)")
    ax.plot(dates, ma7, linestyle="-", label="Moyenne 7 jours")
    ax.set_xlabel("Date")
    ax.set_ylabel("Poids (kg)")
    ax.grid(True)
    ax.legend()
    st.pyplot(fig)

    # Mini stats utiles
    st.markdown("### 📌 Indicateurs")
    dernier = donnees[-1]["poids"]
    premier = donnees[0]["poids"]
    delta = dernier - premier
    st.write(f"- **Dernier poids** : {dernier:.1f} kg")
    st.write(f"- **Évolution depuis le début** : {delta:+.1f} kg")

    if len(donnees) >= 7:
        st.write(f"- **Moyenne 7 jours (actuelle)** : {ma7[-1]:.1f} kg")
else:
    st.info("Ajoute une première mesure pour afficher la courbe.")

st.divider()

# ---------- Tableau + export ----------
st.subheader("📋 Historique")
if donnees:
    st.dataframe(donnees, use_container_width=True)

    # Export CSV
    with open(FICHIER_SUIVI, "rb") as f:
        st.download_button("⬇️ Télécharger le CSV", data=f, file_name="poids_suivi.csv", mime="text/csv")

    colA, colB = st.columns(2)
    with colA:
        if st.button("🗑️ Réinitialiser l'historique"):
            if os.path.exists(FICHIER_SUIVI):
                os.remove(FICHIER_SUIVI)
            st.warning("Historique supprimé. Recharge la page.")
    with colB:
        st.caption("Astuce : pèse-toi le matin, à jeun, mêmes conditions.")
else:
    st.caption("Pas encore d’historique.")
