import json
import random
import pandas as pd
from transformers import pipeline

# =========================
# 1. Load LLM
# =========================
generator = pipeline(
    "text-generation",
    model="mistralai/Mistral-7B-Instruct-v0.2",
    device_map="auto",
    max_new_tokens=700,
    temperature=0.9
)

# =========================
# 2. Prompt
# =========================
PROMPT_TEMPLATE = """
You are generating realistic job postings data for a machine learning dataset.

Return ONLY a valid JSON object (no text outside JSON).

Constraints:
- Ensure ALL fields are coherent and realistic
- Salaries must depend on seniority, location, and experience
- Intern: low salary, Senior/Lead: high salary
- Ensure min_amount <= max_amount
- Currency must match location
- year_exp must match seniority
- description must be realistic and NOT include explicit salary numbers
- Some fields can be null (missing values) when appropriate

JSON format:
{
"id": int,
"title": str,
"company": str,
"location": str,
"date_posted": str,
"job_type": str,
"interval": str,
"min_amount": float,
"max_amount": float,
"currency": str,
"is_remote": bool,
"description": str,
"company_industry": str,
"city": str,
"seniority": str,
"year_exp": int,
"education": str
}

Generate ONE example.
"""

# =========================
# 3. Missing value injection
# =========================
def inject_missing_values(row, missing_prob=0.1):
    for key in row.keys():
        if key in ["id", "min_amount", "max_amount"]:
            continue  # keep essential fields
        if random.random() < missing_prob:
            row[key] = None
    return row

# =========================
# 4. Validation
# =========================
def is_valid(row):
    try:
        if row["min_amount"] > row["max_amount"]:
            return False
        if row["year_exp"] < 0 or row["year_exp"] > 40:
            return False
        if row["seniority"] == "intern" and row["year_exp"] > 2:
            return False
        return True
    except:
        return False

# =========================
# 5. Generate ONE row
# =========================
def generate_one(i):
    prompt = PROMPT_TEMPLATE.replace('"id": int', f'"id": {i}')

    output = generator(prompt)[0]["generated_text"]

    # Extract JSON safely
    try:
        json_str = output.split("{", 1)[1]
        json_str = "{" + json_str
        json_str = json_str[:json_str.rfind("}")+1]
        row = json.loads(json_str)
        return row
    except:
        return None

# =========================
# 6. Generate dataset
# =========================
def generate_dataset(n=3000):
    data = []
    i = 0

    while len(data) < n:
        row = generate_one(i)

        if row and is_valid(row):
            row = inject_missing_values(row, missing_prob=0.15)
            data.append(row)
            i += 1

            if len(data) % 50 == 0:
                print(f"{len(data)} rows generated")

    return pd.DataFrame(data)

# =========================
# 7. Run
# =========================
df = generate_dataset(3000)

df.to_csv("synthetic_jobs.csv", index=False)

print("Dataset ready!")