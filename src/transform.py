import json
import re
import hashlib
import logging
from pathlib import Path
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

# job_hash is built from these fields only — they are the job's content.
# search_role and fetched_at are deliberately excluded: they are the
# pipeline's own metadata, and including them would report false
# "changes" on every run (197 jobs are found under two search terms).
HASH_FIELDS = [
    "title",
    "description",
    "company_name",
    "location_name",
    "salary_min",
    "salary_max",
    "salary_is_predicted",
    "contract_time",
    "category",
    "created",
]


# JSON file load
def load_raw_data(filepath):  # second execute this
    logging.info("Loading raw data...")

    filepath = Path(filepath)

    with open(filepath, "r", encoding="utf-8") as file:
        data = json.load(file)

    # New raw files carry search_role. Old (v1 format) files do not,
    # so derive it from the filename for those.
    search_role = data.get("search_role")

    if not search_role:
        search_role = filepath.stem.replace("jobs_raw_", "").replace("_", " ")
        logging.warning(
            f"'search_role' missing in {filepath.name} — derived '{search_role}' from filename."
        )

    # results convert to DataFrame
    df = pd.json_normalize(data.get("results", []))  # it will convert nested json to flat json

    if df.empty:
        logging.warning("No jobs found.")
        return df

    df = df.rename(columns={
        "company.display_name": "company_name",
        "location.display_name": "location_name",
        "category.label": "category"
    })

    df["search_role"] = search_role

    return df


# remove duplicate jobs
def remove_duplicates(df):  # third execute this

    if "id" in df.columns:
        return df.drop_duplicates(subset="id")

    logging.warning("'id' column not found.")
    return df


# convert salary columns into numeric
def normalize_salary(df):  # fourth execute this
    df["salary_min"] = pd.to_numeric(df.get("salary_min"), errors="coerce")
    df["salary_max"] = pd.to_numeric(df.get("salary_max"), errors="coerce")

    # Adzuna sends 'salary_is_predicted' as a STRING ("0" / "1"), not a
    # number. In Python bool("0") is True, so calling bool() directly is a
    # silent bug — compare against "1" explicitly instead.
    if "salary_is_predicted" in df.columns:
        df["salary_is_predicted"] = (
            df["salary_is_predicted"].astype(str).str.strip() == "1"
        )
    else:
        logging.warning("'salary_is_predicted' column not found — defaulting to False.")
        df["salary_is_predicted"] = False

    return df


# SHA-256 of a job's content, used for change detection
def compute_job_hash(row):

    payload = {}

    for field in HASH_FIELDS:
        value = row.get(field)

        # NaN is not equal to itself, so normalise every missing value to
        # the same placeholder ("") before hashing — otherwise the same job
        # would produce a different hash on every run
        if value is None or pd.isna(value):
            payload[field] = ""
        else:
            payload[field] = str(value)

    # sort_keys=True is required: dict ordering can change, but the hash
    # must stay identical for identical content
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def add_job_hash(df):
    df["job_hash"] = df.apply(compute_job_hash, axis=1)
    return df


# fetching skills from description
def extract_skills(description):  # sixth execute this
    if not isinstance(description, str):
        return []

    skills = []

    for skill in KNOWN_SKILLS:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, description.lower()):
            skills.append(skill)  # keep original casing, not lowercase

    return skills


# all cleaning steps
def clean_jobs(filepath):  # 1FIRST execute this
    df = load_raw_data(filepath)

    if df.empty:
        return df

    df = remove_duplicates(df)
    df = normalize_salary(df)

    if "description" in df.columns:
        df["skills"] = df["description"].apply(extract_skills)  # fifth execute this

    # hash last, once salary has already been normalised to numeric
    df = add_job_hash(df)

    logging.info("Cleaning completed!")
    return df


if __name__ == "__main__":
    from config.settings import RAW_DATA_DIR

    df = clean_jobs(RAW_DATA_DIR / "jobs_raw_data_engineer.json")  # zero execute this

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", None)

    df["hash"] = df["job_hash"].str[:12]

    print(df[
        [
            "title",
            "company_name",
            "search_role",
            "category",
            "salary_is_predicted",
            "hash"
        ]
    ].head())
