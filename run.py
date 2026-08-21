import json
from src.extract import fetch_jobs
from src.transform import clean_jobs
from src.load import get_connection, load_dataframe
from config.settings import RAW_DATA_DIR

SEARCH_TERMS = [
    # Tech roles (20)
    "data engineer",
    "data analyst",
    "data scientist",
    "backend developer",
    "frontend developer",
    "full stack developer",
    "devops engineer",
    "machine learning engineer",
    "software engineer",
    "cloud engineer",
    "android developer",
    "ios developer",
    "qa engineer",
    "database administrator",
    "network engineer",
    "system administrator",
    "ui ux designer",
    "cybersecurity engineer",
    "site reliability engineer",
    "ai engineer",

    # Non-tech roles (10)
    "hr manager",
    "marketing manager",
    "sales executive",
    "accountant",
    "finance analyst",
    "operations manager",
    "content writer",
    "digital marketing specialist",
    "customer support executive",
    "recruiter",
]


conn = get_connection()

for term in SEARCH_TERMS:

    data = fetch_jobs(what=term)

    if data is None:
        print(f"{term} -> fetch failed")
        continue

    safe_query = term.replace(" ", "_").lower()

    df = clean_jobs( RAW_DATA_DIR / f"jobs_raw_{safe_query}.json" )

    if not df.empty:
        load_dataframe(conn, df)

    print(f"{term} -> {len(df)} jobs cleaned and loaded")

conn.close()