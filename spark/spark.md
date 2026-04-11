# spark.md — Plan du pipeline Spark

## Objectif

Lire les fichiers JSON bruts produits par le scraper, les nettoyer,
les enrichir avec les features ML, et produire un fichier Parquet
propre prêt pour la modélisation.

---

## Pourquoi Spark et pas pandas ?

| | pandas | PySpark |
|---|---|---|
| Volume | Limité à la RAM | Distribué, scalable |
| Format de sortie | CSV/Excel | Parquet (colonnaire, compressé, rapide) |
| Contexte académique | Analyse exploratoire | Pipeline Big Data |

Pour un projet Big Data, Spark est la bonne couche de traitement.
Pandas reste utile pour l'EDA et la modélisation (scikit-learn ne parle pas Spark).

---

## Fichier à créer : `spark/clean_jobs.py`

---

## Pipeline prévu

```
data/raw/*.json
      ↓
  [1] LOAD       — Charger tous les JSON en un seul DataFrame Spark
      ↓
  [2] DEDUPLICATE — Supprimer les doublons inter-runs (même job_url)
      ↓
  [3] CLEAN      — Nettoyer les valeurs aberrantes et manquantes
      ↓
  [4] ENRICH     — Extraire les features depuis titre et description
      ↓
  [5] VALIDATE   — Vérifier la qualité finale
      ↓
data/processed/jobs_clean.parquet
```

---

## Détail des traitements par étape

### [1] LOAD — Chargement

Lire tous les fichiers JSON du dossier `data/raw/` en un seul DataFrame.

```python
df = spark.read.option("multiline", "true").json("data/raw/*.json")
```

Colonnes attendues en entrée (produites par le scraper) :
`id`, `site`, `job_url`, `title`, `company`, `location`, `date_posted`,
`job_type`, `interval`, `min_amount`, `max_amount`, `currency`,
`is_remote`, `description`, `salary_source`, `company_industry`

---

### [2] DEDUPLICATE — Déduplication inter-runs

Le scraper déduplique au sein d'un même run, mais si 3 coéquipiers
lancent chacun un run, les mêmes offres peuvent apparaître plusieurs fois.

```python
df = df.dropDuplicates(["job_url"])
```

`job_url` est la clé primaire naturelle d'une offre Indeed.

---

### [3] CLEAN — Nettoyage

#### 3a. Filtrer les salaires aberrants

Indeed publie parfois des salaires horaires sans que `interval` soit correctement renseigné.
Un salaire annuel de $900 ou $5 000 est forcément un salaire horaire mal converti.

```python
# Garder uniquement les salaires annuels plausibles (30k$ - 500k$)
df = df.filter(
    (col("min_amount").isNull()) |
    ((col("min_amount") >= 30_000) & (col("max_amount") <= 500_000))
)
```

#### 3b. Normaliser la colonne `interval`

Convertir tous les salaires en annuel pour homogénéiser.

```python
# Si interval == "hourly" → multiplier par 2080 (52 semaines × 40h)
# Si interval == "monthly" → multiplier par 12
df = df.withColumn("min_amount", when(col("interval") == "hourly", col("min_amount") * 2080)
                                 .when(col("interval") == "monthly", col("min_amount") * 12)
                                 .otherwise(col("min_amount")))
```

#### 3c. Supprimer les lignes sans titre ni description

Les offres sans titre ou sans description sont inexploitables pour le ML.

```python
df = df.filter(col("title").isNotNull() & col("description").isNotNull())
```

#### 3d. Nettoyer les espaces et casses

```python
df = df.withColumn("title", trim(col("title")))
df = df.withColumn("company", trim(col("company")))
```

---

### [4] ENRICH — Feature Engineering

C'est ici que l'on crée les variables qui alimenteront le modèle ML.
Ces traitements sont délibérément absents du scraper pour respecter
la séparation des responsabilités (collecte ≠ traitement).

#### 4a. `city` et `state` — Parsing de la localisation

```python
# "San Francisco, CA, US" → city="San Francisco", state="CA"
df = df.withColumn("city",  split(col("location"), ",").getItem(0))
df = df.withColumn("state", trim(split(col("location"), ",").getItem(1)))
```

#### 4b. `salary_midpoint` — Variable cible du modèle ML

```python
# (min + max) / 2 — ce sera le y à prédire
df = df.withColumn("salary_midpoint",
    when(col("min_amount").isNotNull() & col("max_amount").isNotNull(),
         (col("min_amount") + col("max_amount")) / 2)
    .otherwise(None))
```

#### 4c. `seniority` — Niveau de séniorité depuis le titre

Utiliser une UDF (User Defined Function) Spark avec les mêmes règles que le scraper.

Niveaux : `junior`, `mid`, `senior`, `lead`, `unknown`

Mots-clés par niveau :
- junior : junior, entry, entry-level, associate, jr.
- mid : mid-level, intermediate, level 2
- senior : senior, sr., experienced, level 3
- lead : lead, staff, principal, manager, director, head of, vp, chief

#### 4d. `skills` — Compétences techniques depuis la description

Détecter la présence de ~50 technologies dans le texte de la description.
Retourner une liste (ArrayType) ou une chaîne séparée par des virgules.

Technologies à détecter (catégorisées) :
- Langages : python, sql, scala, java, r, go, c++
- Big Data : spark, kafka, airflow, dbt, databricks, hadoop, flink
- Cloud : aws, gcp, azure, snowflake, redshift, bigquery, s3
- ML : tensorflow, pytorch, scikit-learn, xgboost, lightgbm, mlflow
- IA : llm, nlp, computer vision, deep learning, generative ai, transformers, langchain
- BDD : postgresql, mysql, mongodb, elasticsearch, redis, cassandra
- BI : tableau, power bi, looker
- DevOps : docker, kubernetes, git, terraform, ci/cd

#### 4e. `years_exp` — Années d'expérience requises

Regex sur la description pour extraire l'expérience demandée.

Formats à reconnaître :
- "3-5 years" → 4.0 (moyenne de la fourchette)
- "3+ years of experience" → 3.0
- "minimum 5 years" → 5.0
- "at least 2 years" → 2.0

#### 4f. `education` — Niveau d'études requis

Détecter dans la description : `phd`, `master`, `bachelor`, `unknown`

#### 4g. `skill_count` — Nombre de compétences détectées

Feature numérique simple : plus une offre liste de compétences,
plus le salaire a tendance à être élevé.

```python
df = df.withColumn("skill_count", size(split(col("skills"), ",")))
```

---

### [5] VALIDATE — Contrôle qualité final

Afficher un rapport avant sauvegarde :
- Nombre total de lignes
- % de `salary_midpoint` renseigné (doit être > 80%)
- Distribution des salaires (min, max, moyenne, médiane)
- % de remplissage de chaque feature ML
- Nombre de villes distinctes
- Nombre d'entreprises distinctes

---

## Format de sortie

```python
df.write.mode("overwrite").parquet("data/processed/jobs_clean.parquet")
```

**Pourquoi Parquet ?**
- Format colonnaire : lecture 10× plus rapide que JSON pour le ML
- Compression intégrée : fichier ~5× plus petit que le CSV équivalent
- Schéma typé : les types de colonnes sont préservés (float, bool, date…)
- Standard de facto pour les pipelines Big Data et scikit-learn via pandas

---

## Colonnes finales du dataset `jobs_clean`

| Colonne | Type | Source | Rôle ML |
|---|---|---|---|
| `job_url` | string | scraper | Identifiant (à exclure du modèle) |
| `title` | string | scraper | Feature textuelle |
| `company` | string | scraper | Feature catégorielle |
| `city` | string | Spark | Feature géographique |
| `state` | string | Spark | Feature géographique |
| `is_remote` | bool | scraper | Feature binaire |
| `seniority` | string | Spark | Feature catégorielle |
| `skills` | string | Spark | Feature textuelle (liste) |
| `skill_count` | int | Spark | Feature numérique |
| `years_exp` | float | Spark | Feature numérique |
| `education` | string | Spark | Feature ordinale |
| `job_type` | string | scraper | Feature catégorielle |
| `company_industry` | string | scraper | Feature catégorielle |
| `date_posted` | date | scraper | Feature temporelle |
| `min_amount` | float | scraper/Spark | Info salaire |
| `max_amount` | float | scraper/Spark | Info salaire |
| `salary_midpoint` | float | Spark | **Variable cible (y)** |

---

## Usage prévu

```bash
# Lancer le pipeline Spark (une fois les JSON raw disponibles)
python spark/clean_jobs.py

# Ou via spark-submit pour un vrai contexte distribué
spark-submit spark/clean_jobs.py
```

---

## Ce qui vient ensuite

Une fois `data/processed/jobs_clean.parquet` produit :

```
modeling/salary_predictor.py
  - Lit jobs_clean.parquet via pandas (df = pd.read_parquet(...))
  - Feature engineering final (encodage catégoriel, vectorisation skills)
  - Entraînement modèle (RandomForest, GradientBoosting via scikit-learn)
  - Évaluation (RMSE, R², MAE)
  - Sauvegarde du modèle (.pkl)
```
