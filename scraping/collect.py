"""
collect.py  --  Script unique de collecte des offres Data & IA
==============================================================
Lance les deux sources en sequence et sauvegarde les donnees brutes.

Sources :
  - Indeed USA via JobSpy  (bibliotheque Python, ~1 300 offres, 77% salaires)
  - Adzuna USA via API     (API officielle gratuite, ~5 000 offres, 100% salaires)

Sortie :
  data/raw/indeed_YYYYMMDD_HHMMSS.json   + .csv
  data/raw/adzuna_YYYYMMDD_HHMMSS.json   + .csv

Prerequis :
  Fichier .env a la racine du projet avec :
    ADZUNA_APP_ID=...
    ADZUNA_APP_KEY=...

Usage :
  python scraping/collect.py
  python scraping/collect.py --indeed 1500 --adzuna 5000
"""

import os
import re
import sys
import time
import random
import logging
import argparse
from datetime import datetime
from pathlib import Path

import requests
import pandas as pd
from jobspy import scrape_jobs
from dotenv import load_dotenv

load_dotenv()

# -----------------------------------------------------------------------------
# LOGGING
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# CONFIGURATION COMMUNE AUX DEUX SOURCES
# -----------------------------------------------------------------------------

# Requetes couvrant tous les metiers Data & IA
QUERIES = [
    "data engineer",
    "data scientist",
    "data analyst",
    "machine learning engineer",
    "AI engineer",
    "data architect",
    "MLOps engineer",
    "LLM engineer",
    "analytics engineer",
    "business intelligence engineer",
    "NLP engineer",
    "computer vision engineer",
]

# Filtre sur le titre : "data" ou "ai" en tant que mot entier
# \b = word boundary -- evite "spain" ou "email"
TITLE_FILTER = re.compile(r"\b(data|ai)\b", re.IGNORECASE)

# Villes US -- couvrent les principaux bassins tech (tier 1 a 3)
# Diviser par villes plutot que par pays :
#   - la ville devient une feature ML directement exploitable
#   - les salaires varient fortement selon la ville
US_CITIES = [
    "San Francisco, CA", "New York, NY", "Seattle, WA",
    "Austin, TX", "Boston, MA", "Chicago, IL",
    "Los Angeles, CA", "Washington, DC", "Atlanta, GA", "Dallas, TX",
    "Denver, CO", "Miami, FL", "Phoenix, AZ", "Minneapolis, MN",
    "Portland, OR", "San Diego, CA", "Nashville, TN", "Philadelphia, PA",
    "Detroit, MI", "Charlotte, NC", "Salt Lake City, UT", "Raleigh, NC",
]

# -----------------------------------------------------------------------------
# SOURCE 1 -- INDEED via JobSpy
# -----------------------------------------------------------------------------

def collect_indeed(target: int) -> pd.DataFrame:
    """
    Collecte les offres Indeed en iterant sur toutes les combinaisons
    (ville x requete) jusqu'a atteindre le nombre cible.

    JobSpy gere le scraping Indeed en interne.
    On deduplique par job_url car une meme offre peut remonter
    pour deux requetes differentes.

    Retourne un DataFrame brut (aucune transformation, juste la collecte).
    """
    n_combinations   = len(US_CITIES) * len(QUERIES)
    results_per_call = min(50, max(10, target // n_combinations + 1))

    logger.info("-" * 50)
    logger.info(f"  Indeed  --  cible : {target} offres")
    logger.info(f"  {len(US_CITIES)} villes x {len(QUERIES)} requetes = {n_combinations} appels")
    logger.info("-" * 50)

    frames    = []
    seen_urls = set()
    total     = 0

    for city in US_CITIES:
        if total >= target:
            break
        logger.info(f"  {city}")

        for query in QUERIES:
            if total >= target:
                break

            try:
                df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=query,
                    location=city,
                    results_wanted=results_per_call,
                    country_indeed="usa",
                    description_format="markdown",
                    hours_old=8760,   # toute l'annee disponible sur Indeed
                    verbose=0,
                )
            except Exception as e:
                logger.warning(f"    Erreur [{query}] : {e}")
                continue

            if df is None or df.empty:
                continue

            # Deduplication par URL
            df = df[~df["job_url"].isin(seen_urls)]
            if df.empty:
                continue

            # Filtre sur le titre (collecte uniquement les offres Data/AI)
            df = df[df["title"].apply(
                lambda t: bool(TITLE_FILTER.search(str(t))) if pd.notna(t) else False
            )]
            if df.empty:
                continue

            seen_urls.update(df["job_url"].tolist())
            frames.append(df)
            total += len(df)
            logger.info(f"    [{query}] +{len(df)}  (total : {total})")

    if not frames:
        logger.warning("  Indeed : aucune offre collectee.")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True).drop_duplicates(subset="job_url")
    logger.info(f"  Indeed : {len(result)} offres uniques collectees")
    return result.head(target)


# -----------------------------------------------------------------------------
# SOURCE 2 -- ADZUNA via API officielle
# -----------------------------------------------------------------------------

def collect_adzuna(target: int) -> pd.DataFrame:
    """
    Collecte les offres Adzuna en paginant les resultats de l'API.

    L'API Adzuna est gratuite (250 requetes/jour).
    Chaque page retourne jusqu'a 50 offres.
    On itere sur les requetes et les pages jusqu'a atteindre la cible.

    Retourne un DataFrame brut (meme format que Indeed pour faciliter la fusion dans Spark).
    """
    app_id  = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.error("  ADZUNA_APP_ID / ADZUNA_APP_KEY manquants dans .env")
        return pd.DataFrame()

    logger.info("-" * 50)
    logger.info(f"  Adzuna  --  cible : {target} offres")
    logger.info(f"  {len(QUERIES)} requetes, pagination automatique")
    logger.info("-" * 50)

    all_offers = []
    seen_urls  = set()
    total      = 0

    for query in QUERIES:
        if total >= target:
            break

        logger.info(f"  {query}")
        page = 1

        while total < target:
            url    = f"https://api.adzuna.com/v1/api/jobs/us/search/{page}"
            params = {
                "app_id":               app_id,
                "app_key":              app_key,
                "results_per_page":     50,
                "what":                 query,
                "content-type":         "application/json",
                "salary_include_unknown": 0,
            }

            try:
                response = requests.get(url, params=params, timeout=15)
            except Exception as e:
                logger.warning(f"    Erreur reseau page {page} : {e}")
                break

            if response.status_code == 401:
                logger.error("    Cles API invalides (401)")
                return pd.DataFrame(all_offers)
            if response.status_code == 429:
                logger.warning("    Limite atteinte (429) -- pause 60s")
                time.sleep(60)
                continue
            if response.status_code != 200:
                logger.warning(f"    HTTP {response.status_code} -- arret pagination")
                break

            jobs = response.json().get("results", [])
            if not jobs:
                break

            new = 0
            for job in jobs:
                job_url = job.get("redirect_url", "")
                if not job_url or job_url in seen_urls:
                    continue

                title = job.get("title", "")
                if not TITLE_FILTER.search(str(title)):
                    continue

                seen_urls.add(job_url)
                created = job.get("created", "")
                all_offers.append({
                    "job_url":          job_url,
                    "title":            title,
                    "company":          job.get("company", {}).get("display_name", ""),
                    "location":         job.get("location", {}).get("display_name", ""),
                    "date_posted":      created[:10] if created else None,
                    "min_amount":       float(job["salary_min"]) if job.get("salary_min") else None,
                    "max_amount":       float(job["salary_max"]) if job.get("salary_max") else None,
                    "interval":         "yearly",
                    "currency":         "USD",
                    "description":      job.get("description", ""),
                    "is_remote":        None,
                    "job_type":         job.get("contract_time", ""),
                    "company_industry": job.get("category", {}).get("label", ""),
                    "site":             "adzuna",
                })
                new   += 1
                total += 1

            logger.info(f"    Page {page} : +{new}  (total : {total})")

            if len(jobs) < 50:
                break

            page += 1
            time.sleep(random.uniform(0.5, 1.2))

    if not all_offers:
        logger.warning("  Adzuna : aucune offre collectee.")
        return pd.DataFrame()

    result = pd.DataFrame(all_offers)
    logger.info(f"  Adzuna : {len(result)} offres uniques collectees")
    return result


# -----------------------------------------------------------------------------
# FUSION ET SAUVEGARDE
# -----------------------------------------------------------------------------

def merge_and_save(df_indeed: pd.DataFrame, df_adzuna: pd.DataFrame, output_dir: str = "data/raw") -> None:
    """
    Fusionne Indeed et Adzuna en un seul DataFrame puis sauvegarde en JSON et CSV.

    pd.concat aligne automatiquement les colonnes communes et remplit
    les colonnes manquantes avec NaN (ex: colonnes Indeed absentes d'Adzuna).
    La colonne "site" permet toujours de savoir d'ou vient chaque ligne.
    """
    frames = [df for df in [df_indeed, df_adzuna] if not df.empty]

    if not frames:
        logger.warning("  Aucune donnee a sauvegarder.")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset="job_url")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base      = os.path.join(output_dir, f"jobs_{timestamp}")

    combined.to_json(base + ".json", orient="records", force_ascii=False, indent=2, date_format="iso")
    combined.to_csv(base + ".csv",   index=False, encoding="utf-8-sig")

    logger.info(f"  {len(combined)} offres fusionnees  (Indeed: {len(df_indeed)}, Adzuna: {len(df_adzuna)})")
    logger.info(f"  JSON -> {base}.json")
    logger.info(f"  CSV  -> {base}.csv")


# -----------------------------------------------------------------------------
# RAPPORT QUALITE -- SALAIRES
# -----------------------------------------------------------------------------

def salary_report(indeed: pd.DataFrame, adzuna: pd.DataFrame) -> None:
    """
    Affiche les statistiques descriptives sur les salaires des deux sources.

    Permet de verifier que les donnees collectees sont conformes
    aux niveaux de salaires attendus sur le marche US Data/AI.
    """

    def stats(df, name):
        if df.empty or "min_amount" not in df.columns:
            print(f"  {name} : aucune donnee")
            return

        has_sal = df["min_amount"].notna() & df["max_amount"].notna()
        sub     = df[has_sal].copy()

        # Conversion horaire -> annuel pour Indeed
        if "interval" in sub.columns:
            mask = sub["interval"] == "hourly"
            sub.loc[mask, "min_amount"] *= 2080
            sub.loc[mask, "max_amount"] *= 2080

        sub["midpoint"] = (sub["min_amount"] + sub["max_amount"]) / 2
        sub = sub[(sub["midpoint"] >= 30_000) & (sub["midpoint"] <= 600_000)]

        sal = sub["midpoint"]
        pct = 100 * len(sub) / len(df)

        print(f"\n  -- {name} --")
        print(f"    Offres totales       : {len(df)}")
        print(f"    Avec salaire         : {len(sub)} ({pct:.1f}%)")
        print(f"    Mediane              : ${sal.median():>10,.0f}")
        print(f"    Moyenne              : ${sal.mean():>10,.0f}")
        print(f"    Ecart-type           : ${sal.std():>10,.0f}")
        print(f"    Min                  : ${sal.min():>10,.0f}")
        print(f"    Max                  : ${sal.max():>10,.0f}")
        return sub["midpoint"]

    print("\n" + "=" * 50)
    print("  RAPPORT QUALITE -- SALAIRES")
    print("=" * 50)

    sal_indeed = stats(indeed, "Indeed")
    sal_adzuna = stats(adzuna, "Adzuna")

    # Statistiques combinees
    parts = [s for s in [sal_indeed, sal_adzuna] if s is not None]
    if parts:
        combined = pd.concat(parts)
        bins     = [0, 80_000, 120_000, 150_000, 180_000, 220_000, 10_000_000]
        labels   = ["<80k", "80-120k", "120-150k", "150-180k", "180-220k", ">220k"]

        print(f"\n  -- Combine ({len(combined)} offres avec salaire) --")
        print(f"    Mediane  : ${combined.median():>10,.0f}")
        print(f"    Moyenne  : ${combined.mean():>10,.0f}")

        tranches = pd.cut(combined, bins=bins, labels=labels)
        print(f"\n    Distribution par tranche salariale :")
        for t, n in tranches.value_counts().sort_index().items():
            pct = 100 * n / len(combined)
            bar = "#" * int(pct / 2)
            print(f"      {t:<12} {n:>5} offres  ({pct:.1f}%)  {bar}")

    print("=" * 50 + "\n")


# -----------------------------------------------------------------------------
# POINT D'ENTREE
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Collecte offres Data & IA -- Indeed + Adzuna")
    parser.add_argument("--indeed", type=int, default=1500,
                        help="Offres Indeed cibles (defaut: 1500)")
    parser.add_argument("--adzuna", type=int, default=5000,
                        help="Offres Adzuna cibles (defaut: 5000)")
    parser.add_argument("--output", type=str, default="data/raw",
                        help="Dossier de sortie (defaut: data/raw)")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("  COLLECTE -- Indeed + Adzuna USA")
    logger.info("=" * 50)

    # Collecte Indeed
    df_indeed = collect_indeed(target=args.indeed)

    # Collecte Adzuna
    df_adzuna = collect_adzuna(target=args.adzuna)

    # Fusion et sauvegarde en un seul fichier
    merge_and_save(df_indeed, df_adzuna, output_dir=args.output)

    # Rapport qualite sur les salaires
    salary_report(df_indeed, df_adzuna)

    logger.info("  Collecte terminee. Fichiers disponibles dans : " + args.output)


if __name__ == "__main__":
    main()
