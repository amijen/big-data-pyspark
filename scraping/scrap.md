# scrap.md -- Documentation de la collecte de donnees

## Responsabilite dans le projet

Cette partie couvre uniquement la collecte des donnees brutes.
Aucun traitement, enrichissement ou feature engineering n'est fait ici.
Tout ce qui suit (nettoyage, features, modelisation) est pris en charge par les autres membres.

---

## Script a lancer

Un seul script suffit pour collecter toute la donnee necessaire :

```bash
python scraping/collect.py
```

Options disponibles :
```bash
python scraping/collect.py --indeed 1500 --adzuna 5000 --output data/raw
```

Le script collecte les deux sources en sequence et affiche un rapport
de qualite sur les salaires a la fin.

---

## Ou sont les donnees ?

Toutes les donnees brutes sont dans `data/raw/` (ce dossier est dans `.gitignore`).

```
data/raw/
  indeed_YYYYMMDD_HHMMSS.json     offres Indeed (JSON, format Spark)
  indeed_YYYYMMDD_HHMMSS.csv      meme donnee en CSV (lisible dans Excel)
  adzuna_YYYYMMDD_HHMMSS.json     offres Adzuna (JSON, format Spark)
  adzuna_YYYYMMDD_HHMMSS.csv      meme donnee en CSV
```

Les fichiers sont horodates. Chaque run genere de nouveaux fichiers.
Spark lira `data/raw/*.json` et fusionnera tout automatiquement.

---

## Pourquoi deux sources ?

| Source   | Offres/run | Salaires | Probleme depuis France |
|----------|------------|----------|------------------------|
| Indeed   | ~1 300     | 77%      | Aucun                  |
| Adzuna   | ~5 000     | 100%     | Aucun (vraie API)      |
| LinkedIn | ~1 000     | 0%       | Aucun                  |
| Glassdoor| -          | -        | Erreur 400             |
| ZipRecruiter | -      | -        | Bloque GDPR (IP EU)    |

Indeed et Adzuna sont les deux seules sources qui publient des salaires
de facon fiable depuis une IP francaise.

---

## Statistiques descriptives -- salaires observes

Donnees du run du 11 avril 2026 :

### Indeed (JobSpy)

| Metrique        | Valeur        |
|-----------------|---------------|
| Total offres    | 1 329         |
| Avec salaire    | 1 019 (76.7%) |
| Mediane         | $160 000 / an |
| Moyenne         | $158 780 / an |
| Ecart-type      | $47 391       |
| Min             | $52 500 / an  |
| Max             | $294 750 / an |

Note : 55 offres etaient en salaire horaire, converties en annuel (x 2080h).

### Adzuna (API)

| Metrique        | Valeur        |
|-----------------|---------------|
| Total offres    | 5 000         |
| Avec salaire    | 4 992 (99.8%) |
| Mediane         | $140 657 / an |
| Moyenne         | $146 325 / an |
| Ecart-type      | $46 502       |
| Min             | $33 881 / an  |
| Max             | $454 454 / an |

### Dataset combine (6 011 observations avec salaire)

| Tranche         | Nombre | Part  |
|-----------------|--------|-------|
| < 80 000 $      | 276    | 4.6%  |
| 80 000 - 120 000 $ | 1 480 | 24.6% |
| 120 000 - 150 000 $ | 1 613 | 26.8% |
| 150 000 - 180 000 $ | 1 309 | 21.8% |
| 180 000 - 220 000 $ | 910  | 15.1% |
| > 220 000 $     | 423    | 7.0%  |
| **Total**       | **6 011** | 100% |

**Mediane combinee : $143 398 / an** -- coherent avec les donnees publiques
sur le marche Data/AI aux Etats-Unis (sources : Glassdoor, Levels.fyi).

La distribution est realiste :
- Le gros du marche (80%) se situe entre $80k et $220k
- La queue haute (>220k) correspond aux postes Staff/Principal dans les grandes tech
- La queue basse (<80k) correspond aux postes junior ou localisations moins cheres

---

## Strategie de collecte

### Indeed -- pourquoi rechercher par ville et non par pays ?

Une recherche nationale ("Data Engineer, USA") retourne des resultats
peu diversifies geographiquement. En cherchant ville par ville :
- La ville devient une feature ML directement exploitable
- On couvre la diversite salariale (San Francisco ~30% au-dessus de la moyenne)
- Indeed retourne des resultats plus pertinents

22 villes couvrent les principaux bassins tech US :
- Tier 1 (salaires hauts) : San Francisco, New York, Seattle
- Tier 2 : Austin, Boston, Chicago, Los Angeles, Washington DC, Atlanta, Dallas
- Tier 3 : Denver, Miami, Phoenix, Minneapolis, Portland, San Diego,
           Nashville, Philadelphia, Detroit, Charlotte, Salt Lake City, Raleigh

12 requetes couvrent tous les metiers Data & IA :
data engineer, data scientist, data analyst, machine learning engineer,
AI engineer, data architect, MLOps engineer, LLM engineer,
analytics engineer, business intelligence engineer, NLP engineer,
computer vision engineer.

### Adzuna -- pagination

L'API Adzuna retourne 50 resultats par page.
Le script pagine automatiquement jusqu'a la cible ou jusqu'a
l'epuisement des resultats disponibles.
Limite gratuite : 250 requetes/jour (largement suffisant).

### Filtre sur le titre

Les deux sources appliquent le meme filtre a la collecte :
le titre doit contenir "data" ou "ai" en tant que mot entier.

```python
TITLE_FILTER = re.compile(r"\b(data|ai)\b", re.IGNORECASE)
```

Le `\b` (word boundary) evite les faux positifs :
"spain" ou "email" ne sont pas retenus.

### Deduplication

Chaque source deduplique par `job_url` pendant la collecte.
La deduplication inter-sources (Indeed vs Adzuna) est faite dans Spark.

---

## Colonnes produites

### Indeed (43 colonnes natives JobSpy)

Colonnes principales utilisees par Spark :

| Colonne        | Type    | Description                          |
|----------------|---------|--------------------------------------|
| job_url        | string  | Identifiant unique -- cle primaire   |
| site           | string  | Toujours "indeed"                    |
| title          | string  | Intitule du poste                    |
| company        | string  | Nom de l'entreprise                  |
| location       | string  | "San Francisco, CA, US"              |
| date_posted    | date    | Date de publication                  |
| interval       | string  | yearly / hourly / monthly            |
| min_amount     | float   | Salaire minimum                      |
| max_amount     | float   | Salaire maximum                      |
| is_remote      | bool    | Teletravail autorise                 |
| job_type       | string  | fulltime, parttime...                |
| description    | string  | Description complete (Markdown)      |
| company_industry | string | Secteur d'activite                  |

### Adzuna (15 colonnes)

| Colonne        | Type    | Description                          |
|----------------|---------|--------------------------------------|
| job_url        | string  | Identifiant unique -- cle primaire   |
| site           | string  | Toujours "adzuna"                    |
| title          | string  | Intitule du poste                    |
| company        | string  | Nom de l'entreprise                  |
| location       | string  | Ville (format variable)              |
| date_posted    | date    | Date de publication                  |
| interval       | string  | Toujours "yearly"                    |
| min_amount     | float   | Salaire minimum                      |
| max_amount     | float   | Salaire maximum                      |
| job_type       | string  | full_time, part_time...              |
| description    | string  | Description complete                 |
| company_industry | string | Categorie Adzuna                    |

---

## Separation des responsabilites

Le scraper ne fait que collecter. Il ne transforme pas la donnee.

| Traitement                        | Fait ici | Raison                                  |
|-----------------------------------|----------|-----------------------------------------|
| Filtre titre Data/AI              | Oui      | Filtre de collecte, pas de traitement   |
| Deduplication dans un meme run    | Oui      | Evite de stocker des doublons inutiles  |
| Extraction seniority/skills/etc.  | Non      | Fait par Spark (clean_jobs.py)          |
| Calcul salary_midpoint            | Non      | Fait par Spark (variable cible ML)      |
| Deduplication inter-sources/runs  | Non      | Fait par Spark (dropDuplicates)         |
| Nettoyage des outliers salariaux  | Non      | Fait par Spark                          |

---

## Prerequis techniques

```
pip install python-jobspy requests pandas python-dotenv
```

Fichier `.env` a la racine (ne jamais committer) :
```
ADZUNA_APP_ID=votre_id
ADZUNA_APP_KEY=votre_cle
```

Inscription gratuite sur : https://developer.adzuna.com
