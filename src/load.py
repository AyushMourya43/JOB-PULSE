import logging
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from src import logger
from config.settings import (
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
    DB_SSLMODE,
    RAW_DATA_DIR
)

from src.transform import clean_jobs

# execute_values splits large lists into chunks of this size. One file
# holds at most 400 jobs, so this keeps each batch to a single statement.
BATCH_SIZE = 1000


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode=DB_SSLMODE
    )


def clean_value(value):
    if value is None or pd.isna(value):
        return None
    return value


# ---------------------------------------------------------------
# Pipeline run bookkeeping
#
# The run record is committed on its own, separately from the data load.
# If it shared a transaction with the work it is recording, a rollback
# would erase the evidence that the run ever happened — which is exactly
# when that evidence matters most.
# ---------------------------------------------------------------

def start_pipeline_run(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO pipeline_runs (started_at, status)
            VALUES (CURRENT_TIMESTAMP, 'running')
            RETURNING run_id
            """
        )
        run_id = cur.fetchone()[0]

    conn.commit()

    return run_id


def finish_pipeline_run(conn, run_id, status, totals, error_message=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE pipeline_runs
            SET finished_at    = CURRENT_TIMESTAMP,
                status         = %s,
                jobs_fetched   = %s,
                jobs_inserted  = %s,
                jobs_updated   = %s,
                jobs_unchanged = %s,
                jobs_skipped   = %s,
                error_message  = %s
            WHERE run_id = %s
            """,
            (
                status,
                totals["fetched"],
                totals["inserted"],
                totals["updated"],
                totals["unchanged"],
                totals["skipped"],
                error_message,
                run_id,
            )
        )

    conn.commit()


# ---------------------------------------------------------------
# Lookup caches
#
# Company and skill ids are loaded into dicts once per run and shared
# across every file, so repeated lookups never reach the database.
#
# Note: these caches assume the transaction commits. If a load is rolled
# back, the cached ids no longer exist and the caches must be rebuilt.
# ---------------------------------------------------------------

def load_company_cache(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT name, company_id FROM companies")
        return dict(cur.fetchall())


def load_skill_cache(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT skill_name, skill_id FROM skills")
        return dict(cur.fetchall())


def ensure_companies(cur, names, cache):
    """Insert any company names not already cached, then cache their ids."""

    missing = sorted({n for n in names if n not in cache})

    if not missing:
        return

    execute_values(
        cur,
        "INSERT INTO companies (name) VALUES %s ON CONFLICT (name) DO NOTHING",
        [(n,) for n in missing],
        page_size=BATCH_SIZE
    )

    # ON CONFLICT DO NOTHING returns nothing for rows that already existed,
    # so read the ids back for every name we asked about.
    cur.execute(
        "SELECT name, company_id FROM companies WHERE name = ANY(%s)",
        (missing,)
    )
    cache.update(dict(cur.fetchall()))


def ensure_skills(cur, names, cache):
    """Insert any skill names not already cached, then cache their ids."""

    missing = sorted({n for n in names if n not in cache})

    if not missing:
        return

    execute_values(
        cur,
        "INSERT INTO skills (skill_name) VALUES %s ON CONFLICT (skill_name) DO NOTHING",
        [(n,) for n in missing],
        page_size=BATCH_SIZE
    )

    cur.execute(
        "SELECT skill_name, skill_id FROM skills WHERE skill_name = ANY(%s)",
        (missing,)
    )
    cache.update(dict(cur.fetchall()))


def upsert_jobs(cur, rows):
    """
    Upsert a batch of jobs in one statement.

    rows: list of tuples matching the column list below.
    Returns {external_id: (job_id, status)} for every row the statement
    actually wrote. Rows whose job_hash was unchanged are NOT returned,
    because the WHERE clause blocked the update — the caller resolves
    those separately.
    """

    sql = """
        INSERT INTO jobs
        (
            external_id,
            title,
            description,
            redirect_url,
            company_id,
            location,
            salary_min,
            salary_max,
            salary_is_predicted,
            posted_date,
            contract_time,
            category,
            search_role,
            job_hash,
            source
        )
        VALUES %s

        ON CONFLICT (external_id) DO UPDATE
        SET
            title               = EXCLUDED.title,
            description         = EXCLUDED.description,
            redirect_url        = EXCLUDED.redirect_url,
            company_id          = EXCLUDED.company_id,
            location            = EXCLUDED.location,
            salary_min          = EXCLUDED.salary_min,
            salary_max          = EXCLUDED.salary_max,
            salary_is_predicted = EXCLUDED.salary_is_predicted,
            posted_date         = EXCLUDED.posted_date,
            contract_time       = EXCLUDED.contract_time,
            category            = EXCLUDED.category,
            search_role         = EXCLUDED.search_role,
            job_hash            = EXCLUDED.job_hash,
            updated_at          = CURRENT_TIMESTAMP

        -- Only write when the content actually changed.
        -- IS DISTINCT FROM (rather than !=) because existing rows can have
        -- a NULL job_hash, and NULL != 'abc' evaluates to NULL, not TRUE.
        WHERE jobs.job_hash IS DISTINCT FROM EXCLUDED.job_hash

        -- xmax is 0 on a fresh insert and non-zero on a conflict update.
        RETURNING external_id, job_id, (xmax = 0) AS inserted
    """

    returned = execute_values(cur, sql, rows, page_size=BATCH_SIZE, fetch=True)

    return {
        external_id: (job_id, "inserted" if inserted else "updated")
        for external_id, job_id, inserted in returned
    }


def load_dataframe(conn, df, company_cache=None, skill_cache=None):
    """
    Load one DataFrame. Does NOT commit — the caller owns the transaction,
    so it can decide whether a failure later in the run should roll this
    work back.
    """

    # Build the caches here if the caller did not supply them. run_pipeline()
    # passes them in so they are shared across every DataFrame in a run.
    if company_cache is None:
        company_cache = load_company_cache(conn)
    if skill_cache is None:
        skill_cache = load_skill_cache(conn)

    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    with conn.cursor() as cur:

        # -------------------------------------------------------
        # 1. Collect the rows worth loading
        #
        # Nothing touches the database in this pass — it only shapes the
        # DataFrame into plain Python values so the batches below can be
        # sent in one statement each.
        # -------------------------------------------------------

        records = []

        for _, row in df.iterrows():

            company_name = clean_value(row.get("company_name"))

            if company_name is None:
                logging.warning(
                    f"Skipping job because company name is missing: {row.get('title')}"
                )
                counts["skipped"] += 1
                continue

            posted_date = clean_value(row.get("created"))

            if posted_date:
                posted_date = posted_date[:10]

            records.append({
                "external_id": str(clean_value(row.get("id"))),
                "title": clean_value(row.get("title")),
                "description": clean_value(row.get("description")),
                "redirect_url": clean_value(row.get("redirect_url")),
                "company_name": company_name,
                "location": clean_value(row.get("location_name")),
                "salary_min": clean_value(row.get("salary_min")),
                "salary_max": clean_value(row.get("salary_max")),
                # must be a real Python bool: psycopg2 cannot adapt
                # numpy.bool_ (numpy.float64 works because it subclasses
                # float; numpy.bool_ does not subclass bool)
                "salary_is_predicted": bool(row.get("salary_is_predicted", False)),
                "posted_date": posted_date,
                "contract_time": clean_value(row.get("contract_time")),
                "category": clean_value(row.get("category")),
                "search_role": clean_value(row.get("search_role")),
                "job_hash": clean_value(row.get("job_hash")),
                "skills": list(row.get("skills", [])),
            })

        if not records:
            logging.info(f"Loaded 0 jobs — {counts['skipped']} skipped.")
            return counts

        # -------------------------------------------------------
        # 2. Make sure every company and skill has an id
        # -------------------------------------------------------

        ensure_companies(cur, [r["company_name"] for r in records], company_cache)
        ensure_skills(cur, {s for r in records for s in r["skills"]}, skill_cache)

        # -------------------------------------------------------
        # 3. Upsert every job in one statement
        #
        # remove_duplicates() already dropped repeated ids within this
        # file, which matters here: ON CONFLICT DO UPDATE raises
        # "cannot affect row a second time" if the same key appears twice
        # in a single VALUES list.
        # -------------------------------------------------------

        job_rows = [
            (
                r["external_id"],
                r["title"],
                r["description"],
                r["redirect_url"],
                company_cache[r["company_name"]],
                r["location"],
                r["salary_min"],
                r["salary_max"],
                r["salary_is_predicted"],
                r["posted_date"],
                r["contract_time"],
                r["category"],
                r["search_role"],
                r["job_hash"],
                "adzuna",
            )
            for r in records
        ]

        written = upsert_jobs(cur, job_rows)

        # -------------------------------------------------------
        # 4. Resolve the rows the upsert deliberately skipped
        #
        # An unchanged job produces no RETURNING row, so its job_id is
        # still needed to link skills. One query covers all of them.
        # -------------------------------------------------------

        unchanged_ids = [
            r["external_id"] for r in records if r["external_id"] not in written
        ]

        if unchanged_ids:
            cur.execute(
                "SELECT external_id, job_id FROM jobs WHERE external_id = ANY(%s)",
                (unchanged_ids,)
            )
            for external_id, job_id in cur.fetchall():
                written[external_id] = (job_id, "unchanged")

        # -------------------------------------------------------
        # 5. Link jobs to skills in one statement
        # -------------------------------------------------------

        links = [
            (written[r["external_id"]][0], skill_cache[skill])
            for r in records
            if r["external_id"] in written
            for skill in r["skills"]
        ]

        if links:
            execute_values(
                cur,
                "INSERT INTO job_skills (job_id, skill_id) VALUES %s "
                "ON CONFLICT DO NOTHING",
                links,
                page_size=BATCH_SIZE
            )

        for _, status in written.values():
            counts[status] += 1

    logging.info(
        f"Loaded {len(df)} jobs — "
        f"{counts['inserted']} inserted, {counts['updated']} updated, "
        f"{counts['unchanged']} unchanged, {counts['skipped']} skipped."
    )

    return counts


def run_pipeline(conn, dataframes):
    """
    Load a stream of DataFrames as one tracked pipeline run.

    dataframes: an iterable of (label, DataFrame). The caller decides
    where they come from — freshly fetched from the API, or read back
    from raw files on disk — so this function stays the single place
    that owns the transaction and the run record.
    """

    run_id = start_pipeline_run(conn)
    logging.info(f"Pipeline run {run_id} started.")

    totals = {"fetched": 0, "inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    status = "failed"
    error_message = None

    try:
        # Built once and reused for every DataFrame in this run
        company_cache = load_company_cache(conn)
        skill_cache = load_skill_cache(conn)

        logging.info(
            f"Loaded caches — {len(company_cache)} companies, {len(skill_cache)} skills."
        )

        for label, df in dataframes:

            logging.info(f"Processing {label}")

            if df is None or df.empty:
                continue

            counts = load_dataframe(conn, df, company_cache, skill_cache)

            # Commit per DataFrame. The loader is idempotent, so keeping
            # the work already done is better than discarding all of it
            # because a later one failed — a re-run fixes the rest.
            conn.commit()

            totals["fetched"] += len(df)
            for key in ("inserted", "updated", "unchanged", "skipped"):
                totals[key] += counts[key]

        status = "success"

    except Exception as error:
        conn.rollback()
        error_message = f"{type(error).__name__}: {error}"
        logging.exception("Pipeline run failed.")
        raise

    finally:
        # Runs on success, on failure, and on an unhandled exception, so a
        # run record is never left dangling at 'running'.
        try:
            finish_pipeline_run(conn, run_id, status, totals, error_message)
            logging.info(
                f"Pipeline run {run_id} finished — status={status}, "
                f"{totals['inserted']} inserted, {totals['updated']} updated, "
                f"{totals['unchanged']} unchanged, {totals['skipped']} skipped."
            )
        except Exception:
            # Never let bookkeeping hide the original failure
            logging.exception("Could not record the pipeline run outcome.")

    return totals


def main():
    """Load every raw file already on disk, without calling the API."""

    conn = get_connection()

    try:
        run_pipeline(
            conn,
            ((path.name, clean_jobs(path)) for path in RAW_DATA_DIR.glob("*.json"))
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
