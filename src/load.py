import logging
import pandas as pd
import psycopg2
from src import logger
from config.settings import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    RAW_DATA_DIR
)

from src.transform import clean_jobs

def get_connection():  #second it will execute
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


def clean_value(value):   # fourth it will execute 
    if value is None or pd.isna(value):
        return None
    return value


def get_company_id(conn, company_name): #fifth it will execute 

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO companies (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """,
        (company_name,)
    )

    cur.execute(
        """
        SELECT company_id
        FROM companies
        WHERE name = %s
        """,
        (company_name,)
    )

    company_id = cur.fetchone()[0]

    cur.close()

    return company_id


def get_skill_id(conn, skill_name): # seventh it will execute 

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO skills (skill_name)
        VALUES (%s)
        ON CONFLICT (skill_name) DO NOTHING
        """,
        (skill_name,)
    )

    cur.execute(
        """
        SELECT skill_id
        FROM skills
        WHERE skill_name = %s
        """,
        (skill_name,)
    )

    skill_id = cur.fetchone()[0]

    cur.close()

    return skill_id


def get_job_id(
    conn,
    external_id,
    title,
    company_id,
    location,
    salary_min,
    salary_max,
    posted_date
):  # sixth it will execute=-

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO jobs
        (
            external_id,
            title,
            company_id,
            location,
            salary_min,
            salary_max,
            posted_date,
            source
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

        ON CONFLICT (external_id) DO NOTHING
        """,
        (
            external_id,
            title,
            company_id,
            location,
            salary_min,
            salary_max,
            posted_date,
            "adzuna"
        )
    )

    cur.execute(
        """
        SELECT job_id
        FROM jobs
        WHERE external_id = %s
        """,
        (external_id,)
    )

    job_id = cur.fetchone()[0]

    cur.close()

    return job_id


def link_job_skill(conn, job_id, skill_id): #Eight it will execute 

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO job_skills (job_id, skill_id)
        VALUES (%s, %s)

        ON CONFLICT (job_id, skill_id) DO NOTHING
        """,
        (job_id, skill_id)
    )

    cur.close()


def load_dataframe(conn, df): # third it will execute 

    for _, row in df.iterrows():

        # -------------------------
        # 1. Company
        # -------------------------

        company_name = clean_value(
            row.get("company_name")
        )
        if company_name is None:
             logging.warning(f"Skipping job because company name is missing: {row.get('title')}")
             continue

        company_id = get_company_id(
            conn,
            company_name
        )

        # -------------------------
        # 2. Posted date
        # -------------------------

        posted_date = clean_value(
            row.get("created")
        )

        if posted_date:
            posted_date = posted_date[:10]

        # -------------------------
        # 3. Job
        # -------------------------

        job_id = get_job_id(
            conn,
            external_id=str(clean_value(row.get("id"))),
            title=clean_value(row.get("title")),
            company_id=company_id,
            location=clean_value(row.get("location_name")),
            salary_min=clean_value(row.get("salary_min")),
            salary_max=clean_value(row.get("salary_max")),
            posted_date=posted_date
        )

        # -------------------------
        # 4. Skills
        # -------------------------

        skills = row.get("skills", [])

        for skill in skills:

            skill_id = get_skill_id(
                conn,
                skill
            )

            link_job_skill(
                conn,
                job_id,
                skill_id
            )

    conn.commit()

    logging.info(
        f"Loaded {len(df)} jobs into database."
    )


def main():    # first it will execute

    conn = get_connection()  

    for filepath in RAW_DATA_DIR.glob("*.json"):

        logging.info(
            f"Processing {filepath.name}"
        )

        df = clean_jobs(filepath)

        if not df.empty:
            load_dataframe(conn, df) 

    conn.close()

    logging.info(
        "All files loaded successfully."
    )


if __name__ == "__main__":
    main()