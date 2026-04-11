import pandas as pd
import random
from datetime import datetime, timedelta
from transformers import pipeline
from tqdm import tqdm
import torch

device = 0 if torch.cuda.is_available() else -1
print("GPU available:", torch.cuda.is_available())

N_ROWS = 3000

# ---------------------------
# STATIC DATA
# ---------------------------
titles = ["Data Scientist", "Data Engineer", "ML Engineer", "AI Researcher", "Data Analyst"]
companies = ["Google", "Amazon", "Microsoft", "Meta", "Airbus", "BNP Paribas"]
locations = ["Paris", "London", "Berlin", "New York", "Madrid"]
job_types = ["full-time", "part-time", "internship"]
industries = ["Tech", "Finance", "Industrial", "Consulting"]
seniority_levels = ["intern", "junior", "senior", "lead"]
education_levels = ["bachelor", "master", "phd", "unknown"]
currencies = ["EUR", "USD", "GBP"]

# ---------------------------
# SALARY LOGIC 
# ---------------------------
def generate_salary(seniority):
    if seniority == "intern":
        return random.randint(800, 2000), random.randint(2000, 3000)
    elif seniority == "junior":
        return random.randint(30000, 45000), random.randint(45000, 60000)
    elif seniority == "senior":
        return random.randint(60000, 80000), random.randint(80000, 110000)
    else:
        return random.randint(90000, 120000), random.randint(120000, 160000)

# ---------------------------
# GENERATE STRUCTURED DATA
# ---------------------------
rows = []

for i in range(N_ROWS):
    seniority = random.choice(seniority_levels)
    min_salary, max_salary = generate_salary(seniority)

    row = {
        "id": i,
        "title": random.choice(titles),
        "company": random.choice(companies),
        "location": random.choice(locations),
        "date_posted": (datetime.today() - timedelta(days=random.randint(0, 365))).strftime("%Y-%m-%d"),
        "job_type": random.choice(job_types),
        "interval": "yearly",
        "min_amount": min_salary,
        "max_amount": max_salary,
        "currency": random.choice(currencies),
        "is_remote": random.choice([True, False]),
        "company_industry": random.choice(industries),
        "city": random.choice(locations),
        "seniority": seniority,
        "year_exp": random.randint(0, 12),
        "education": random.choice(education_levels),
    }
    rows.append(row)

df = pd.DataFrame(rows)

# ---------------------------
# GENERATE DESCRIPTIONS (template-based, instant)
# ---------------------------
import random

TEMPLATES = {
    "Data Scientist": [
        "Apply statistical modeling and machine learning to extract insights from large datasets. "
        "Collaborate with engineering and product teams to deploy predictive models into production. "
        "Communicate findings clearly through data visualizations and business recommendations.",

        "Design and implement machine learning pipelines to solve complex business problems. "
        "Perform exploratory data analysis, feature engineering, and model evaluation. "
        "Present results to stakeholders and drive data-informed decision making.",

        "Develop statistical models and ML algorithms to support product and growth initiatives. "
        "Work cross-functionally with data engineers to ensure data quality and availability. "
        "Monitor model performance in production and iterate based on real-world feedback.",
    ],
    "Data Engineer": [
        "Build and maintain scalable data pipelines to collect, transform, and store large volumes of data. "
        "Design data warehouse schemas and optimize query performance for analytical workloads. "
        "Collaborate with data scientists and analysts to ensure reliable data availability.",

        "Develop ETL workflows using modern orchestration tools such as Airflow or dbt. "
        "Maintain cloud-based data infrastructure on AWS, GCP, or Azure. "
        "Ensure data reliability, lineage, and governance across the organization.",

        "Architect and implement real-time and batch data processing systems at scale. "
        "Partner with software engineers to integrate data systems into core products. "
        "Define best practices for data modeling, testing, and pipeline observability.",
    ],
    "ML Engineer": [
        "Train, evaluate, and deploy machine learning models in scalable production environments. "
        "Build ML infrastructure including feature stores, model registries, and serving APIs. "
        "Work closely with researchers to bridge the gap between experimentation and deployment.",

        "Develop end-to-end machine learning systems from data ingestion to model serving. "
        "Optimize model latency and throughput to meet production SLA requirements. "
        "Implement CI/CD pipelines for automated model training and deployment.",

        "Design robust ML platforms that enable rapid experimentation and reliable deployment. "
        "Collaborate with data scientists to productionize models at scale. "
        "Monitor model drift and maintain model quality in live systems.",
    ],
    "AI Researcher": [
        "Conduct original research on deep learning, NLP, or computer vision to advance the state of the art. "
        "Publish findings in top-tier academic venues and open-source key contributions. "
        "Collaborate with applied teams to transfer research breakthroughs into real products.",

        "Explore novel model architectures and training methods to push performance boundaries. "
        "Design rigorous experiments, analyze results, and iterate on hypotheses rapidly. "
        "Stay current with the latest literature and contribute new ideas to the research community.",

        "Lead research projects on foundational AI topics aligned with long-term product goals. "
        "Mentor junior researchers and foster a culture of intellectual curiosity. "
        "Engage with external academic partners and represent the company at conferences.",
    ],
    "Data Analyst": [
        "Analyze business data to identify trends, patterns, and actionable opportunities. "
        "Build dashboards and reports using tools such as Tableau, Looker, or Power BI. "
        "Partner with business stakeholders to define KPIs and measure initiative performance.",

        "Translate complex data into clear narratives that drive strategic decisions. "
        "Write SQL queries and Python scripts to aggregate and clean large datasets. "
        "Collaborate with product and marketing teams on A/B test analysis and reporting.",

        "Own analytical deep-dives across key business areas including growth, retention, and revenue. "
        "Maintain data documentation and ensure consistency of metrics across teams. "
        "Proactively surface insights that influence product roadmap and operational priorities.",
    ],
}

def generate_description(title, seniority, company, location):
    base = random.choice(TEMPLATES.get(title, TEMPLATES["Data Analyst"]))
    prefix_map = {
        "intern":  f"As an intern at {company} in {location}, you will ",
        "junior":  f"Join {company} in {location} as a junior team member. ",
        "senior":  f"We are looking for a senior {title} at {company} ({location}). ",
        "lead":    f"Lead a high-impact team at {company} in {location}. ",
    }
    prefix = prefix_map.get(seniority, "")
    return prefix + base

df["description"] = [
    generate_description(row["title"], row["seniority"], row["company"], row["location"])
    for _, row in df.iterrows()
]

print(f"Generated {len(df)} descriptions in seconds.")
print(df["description"].iloc[0])

df.to_csv("/kaggle/working/synthetic_jobs_fast.csv", index=False)