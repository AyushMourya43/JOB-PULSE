import json
import re
import logging
import pandas as pd
from src import logger

KNOWN_SKILLS = [
    # Tech skills
    "Python", "SQL", "Java", "AWS", "Azure", "GCP", "Docker", "Kubernetes",
    "Spark", "Airflow", "Kafka", "PostgreSQL", "MySQL", "MongoDB", "React",
    "Node.js", "Excel", "Power BI", "Tableau", "Pandas", "NumPy", "ETL",
    "Machine Learning", "Git", "Linux", "Scala", "Hadoop", "Snowflake",

    # Non-tech skills
    "Communication", "Negotiation", "Leadership", "CRM", "Salesforce",
    "SAP", "GAAP", "SEO", "Recruitment", "Payroll", "Budgeting",
    "Forecasting", "Stakeholder Management", "Content Writing",
    "Digital Marketing", "Customer Service", "Team Management",
    "Presentation", "Project Management",
]


# JSON file load
def load_raw_data(filepath):  # second execute this
    logging.info("Loading raw data...")

    with open(filepath, "r", encoding="utf-8") as file:
        data = json.load(file)

    # results convert to DataFrame
    df = pd.json_normalize(data.get("results", []))  # it will convert nested json to flat json

    if df.empty:
        logging.warning("No jobs found.")
        return df

    df = df.rename(columns={
        "company.display_name": "company_name",
        "location.display_name": "location_name"
    })

    return df


# Duplicate jobs REMOVE
def remove_duplicates(df):  # third execute this

    if "id" in df.columns:
        return df.drop_duplicates(subset="id")

    logging.warning("'id' column not found.")
    return df


# convert Salary columns into  numberic 
def normalize_salary(df):  # fourth execute this
    df["salary_min"] = pd.to_numeric(df.get("salary_min"), errors="coerce")
    df["salary_max"] = pd.to_numeric(df.get("salary_max"), errors="coerce")
    return df


# fetching skills from description
def extract_skills(description):  # sixth execute this
    if not isinstance(description, str):
        return []

    skills = []

    for skill in KNOWN_SKILLS:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, description.lower()):
            skills.append(skill)  # not store in lower case 

    return skills


# all cleaning 
def clean_jobs(filepath):  # 1FIRST execute this
    df = load_raw_data(filepath)

    if df.empty:
        return df

    df = remove_duplicates(df)
    df = normalize_salary(df)

    if "description" in df.columns:
        df["skills"] = df["description"].apply(extract_skills)  # fifth execute this

    logging.info("Cleaning completed!")
    return df


if __name__ == "__main__":
    from config.settings import RAW_DATA_DIR

    df = clean_jobs(RAW_DATA_DIR / "jobs_raw_data_engineer.json")  # zero execute this

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    print(df[
        [
            "title",
            "company_name",
            "salary_min",
            "salary_max",
            "skills"
        ]
    ].head())