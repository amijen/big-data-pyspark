# Big Data — Marché de l'emploi tech en France

Pipeline Big Data end-to-end : collecte d'offres d'emploi, traitement Spark, prédiction de salaire.

---

## Pipeline

```
scraping/collect.py
      │
      ▼
data/raw/jobs_*.json + jobs_*.csv        (5 576 offres)
      │
      ▼
spark/analysis.ipynb                     (nettoyage, feature engineering, LLM imputation)
      │
      ├──▶ spark/final.parquet           (offres avec salaire connu)
      └──▶ spark/to_predict.parquet      (offres sans salaire → à prédire)
                │
                ├──▶ spark/nlp_analysis.ipynb          (top-K mots, analyse RDD)
                └──▶ modeling_ML/salary_predictor.ipynb (Random Forest, GBT, Régression)
```

---

## Lancer le projet

### 1. Installation

```bash
pip install -r requirements.txt
```

> Ou utiliser le devcontainer (`.devcontainer/`) sous VS Code.

### 2. Scraping

```bash
python scraping/collect.py
```

Génère `data/raw/jobs_<timestamp>.json` et `data/raw/jobs_<timestamp>.csv`.

> Configurer les clés API dans un fichier `.env` à la racine.

### 3. Traitement Spark

Ouvrir et exécuter **`spark/analysis.ipynb`** dans l'ordre des cellules.

- Lit `data/raw/jobs_*.json`
- Nettoie, normalise, impute les valeurs manquantes (règles + LLM HuggingFace)
- Exporte `spark/final.parquet` et `spark/to_predict.parquet`

> Variable d'environnement requise : `HF_TOKEN` (token HuggingFace pour l'imputation LLM)

### 4. Analyse NLP

Ouvrir et exécuter **`spark/nlp_analysis.ipynb`**.

- Lit les parquets générés à l'étape 3
- Calcule les top-K mots des descriptions via MapReduce (PySpark RDD)

### 5. Modélisation ML

Ouvrir et exécuter **`modeling_ML/salary_predictor.ipynb`**.

- Lit `spark/final.parquet` et `spark/to_predict.parquet`
- Entraîne Random Forest, GBT et Régression Linéaire (Spark ML)
- Prédit les salaires manquants

---

## Structure

```
projet_big_data/
├── scraping/
│   └── collect.py              # Étape 1 : collecte (JobSpy)
├── data/
│   └── raw/                    # JSON + CSV bruts (gitignored)
├── spark/
│   ├── analysis.ipynb          # Étape 2 : nettoyage Spark
│   ├── nlp_analysis.ipynb      # Étape 3 : NLP / MapReduce
│   ├── final.parquet/          # Dataset nettoyé
│   └── to_predict.parquet/     # Dataset à prédire
├── modeling_ML/
│   └── salary_predictor.ipynb  # Étape 4 : prédiction salaire
├── .devcontainer/              # Environnement Docker (VS Code)
├── requirements.txt
└── .gitignore
```

---

## Stack

| Couche | Technologie |
|---|---|
| Scraping | JobSpy (Python) |
| Traitement | PySpark 3.5 |
| Imputation | HuggingFace (Mistral-7B) |
| Modélisation | Spark ML (RF, GBT, LR) |
| Environnement | Docker / devcontainer |
