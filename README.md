# JobPulse — Job Market Skill & Salary Analytics

**Version 1.1**

A data pipeline that pulls live job postings from the Adzuna API, cleans and structures the data with pandas, and loads it into a normalized PostgreSQL database — showing which technical and non-technical skills are in demand, how they cluster together, and what salaries look like across roles and locations in the Indian job market.

**v1.0 Tableau dashboard:** https://public.tableau.com/app/profile/ayush.mourya/viz/JobPulse-JobMarketSkillSalaryAnalytics/Dashboard1

---

## What It Does

- Fetches job postings for 30 roles (20 tech + 10 non-tech) from the Adzuna API, with pagination, retries, and rate limiting
- Cleans the raw data: removes duplicates, normalizes salary fields, extracts skills from job descriptions using a curated skill list
- Computes a content hash per posting so re-runs only write rows that actually changed
- Loads into a normalized PostgreSQL schema (`companies`, `jobs`, `skills`, `job_skills`)
- Records every execution in a `pipeline_runs` table — start, finish, status, row counts, and the error if it failed
- Answers analysis questions with SQL: top in-demand skills, salary trends by location, skills that most often appear together

## Architecture

Current:

```
Adzuna API  ->  Python (extract / transform / load)  ->  PostgreSQL
```

Planned (see Roadmap):

```
Adzuna API -> Python -> Kafka -> AWS S3 (bronze/silver/gold) -> PySpark
                                                                  |
                                                                  v
                          HTML + CSS dashboard  <-  Flask API  <- PostgreSQL
                                                        ^
                                                        |
                                              RAG career advisor
```

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.14 |
| Data collection | `requests`, Adzuna API |
| Data manipulation | `pandas` |
| Database | PostgreSQL 16 |
| DB access | `psycopg2` (batched with `execute_values`) |
| Config | `python-dotenv` |
| Analysis | SQL (joins, GROUP BY, self-joins) |
| Dashboard | Tableau Public (v1.0); HTML + CSS planned |

## Usage

```bash
# Load the raw files already on disk. No API calls, so it costs no quota.
python run.py --skip-fetch

# One role, one page = a single API call
python run.py --roles "data engineer" --max-pages 1

# Only the tech group, 3 pages each = 60 API calls
python run.py --groups tech --max-pages 3

# Everything: 30 roles x 8 pages = 240 API calls
python run.py
```

Search terms live in `config/search_terms.json`, not in code, so adding a role does not mean touching Python. `--max-pages` is the lever for staying inside the Adzuna quota.

## Data Volume

Measured on the current database:

- **11,974 jobs** across **5,668 companies** and **30 search roles**
- **47 skills** tracked, forming **7,632 job-skill relationships**
- 30 raw JSON files, up to 400 postings each

## Data Quality Notes (Read Before Trusting the Numbers)

Real job market data is messy. This project surfaces that rather than hiding it.

- **Every description is truncated at 500 characters.** This is Adzuna's limit, not a sampling artifact — the average description length is 494 characters and most sit exactly at the cap. Skill extraction therefore only sees the opening paragraph of each posting, so the skill counts are a floor, not a true count.
- **Salary coverage is 36%** (4,314 of 11,974 postings). Salary figures are computed over that subset only. Any salary figure shown anywhere should carry its sample size.
- **`salary_is_predicted` is `false` for all 11,974 rows.** Adzuna does not flag any posting in this dataset as an estimate. The column is kept because the API can return `"1"`, but no analysis should be built on it today. (v1.0 of this README claimed some postings were flagged; that was wrong.)
- **~225 postings per run have no company name** — mostly staffing agency listings that do not disclose the hiring company. These are skipped rather than loaded under a placeholder name.
- **652 jobs in the database are no longer returned by the API.** Their listings expired between fetches. This is direct evidence of survivorship bias: a chart of postings over `posted_date` will understate older months, because old listings disappear rather than accumulate. Genuine trend data requires tracking `fetched_at` across many runs, which starts from v1.1 onward.
- **197 postings are found under two different search terms** (for example one listing matching both `accountant` and `recruiter`). Only one `search_role` is stored per job. Modelling this properly needs a `job_search_roles` junction table; at 1.7% of the data it is not worth the complexity yet.
- **10 postings are exact duplicates with different Adzuna IDs** — the same job posted twice by the same company, given adjacent IDs. They are detectable via `job_hash` and could be collapsed in a future gold layer.

## What's New in v1.1

v1.0 fetched data and inserted it. v1.1 turns that into a pipeline that can be re-run safely, observed, and moved to a hosted database.

**Change detection.** Each posting gets a SHA-256 `job_hash` over its content fields. `ON CONFLICT DO UPDATE ... WHERE jobs.job_hash IS DISTINCT FROM EXCLUDED.job_hash` means a re-run writes only the rows that actually changed. `search_role` and `fetched_at` are deliberately excluded from the hash: pipeline metadata in a content hash would report false changes on every run.

**Observability.** Every execution writes a `pipeline_runs` row with status, duration, and per-outcome counts (`inserted` / `updated` / `unchanged` / `skipped`). The record is committed in its own transaction, so a failed load cannot erase the evidence that it ran, and it is finalised in a `finally` block so a crashed run is never left at `running`.

**Batched writes.** Companies, skills, job upserts and skill links each go in a single `execute_values` statement, and lookup ids are cached in memory across the whole run.

| | Queries per file | Per full run |
|---|---|---|
| v1.0 | 3,625 | 108,750 |
| + caching | 1,475 | 44,250 |
| + batching | **3** | **90** |

On localhost that is 7 seconds either way. It matters for the move to a hosted database, where a 20 ms round trip turns 108,750 queries into 36 minutes and 90 queries into about 2 seconds.

**Three fetch bugs fixed.** An empty results page broke the retry loop instead of the pagination loop, so exhausted searches kept requesting pages that could not exist — wasted quota on every role with fewer than 400 postings. A failed page discarded every page already collected. Timeouts and connection errors were not retried at all, so one network blip failed a whole role.

**Richer schema.** `description` (needed for the planned RAG layer), `redirect_url` (the "Apply" link), `contract_time`, `category`, and `salary_is_predicted` are now captured. Adzuna sends `salary_is_predicted` as the string `"0"`, and `bool("0")` is `True` in Python — it is compared against `"1"` explicitly.

**Deployable configuration.** Every setting has a default and a validation error that names the variable, `sslmode` is configurable for hosted Postgres, and logs go to stdout as well as a file, because that is what CI and container platforms capture.

## Project Structure

```
job-pulse-v2/
├── config/
│   ├── settings.py          # env loading, defaults, validation
│   └── search_terms.json    # the 30 search roles, grouped tech / non_tech
├── src/
│   ├── logger.py            # file + stdout logging
│   ├── extract.py           # Adzuna fetch, pagination, retries
│   ├── transform.py         # cleaning, dedup, skill extraction, job_hash
│   └── load.py              # batched upserts, caches, pipeline run tracking
├── sql/
│   ├── schema.sql           # table definitions
│   └── queries.sql          # analysis queries
├── data/
│   ├── raw/                 # raw API responses (gitignored)
│   └── processed/           # exported CSV (gitignored)
├── logs/                    # daily log files (gitignored)
├── run.py                   # pipeline entry point
├── requirements.txt
└── .env.example
```

## Setup

1. Clone the repo and create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your Adzuna API credentials (free signup at [developer.adzuna.com](https://developer.adzuna.com/)) and PostgreSQL connection details.
4. Create the database and run the schema:
   ```bash
   createdb jobpulse
   psql -d jobpulse -f sql/schema.sql
   ```
5. Run the pipeline:
   ```bash
   python run.py
   ```

## Roadmap

- **v1.0** — local ETL pipeline, normalized Postgres schema, SQL analysis, published Tableau dashboard
- **v1.1 (current)** — idempotent upserts with change detection, run tracking, batched writes, fetch reliability fixes, config validation
- **Phase 1.5** — hosted Postgres (Neon), scheduled runs via GitHub Actions, pytest suite in CI
- **Phase 2** — Kafka between ingestion and storage, for sources that arrive continuously rather than on a schedule
- **Phase 3** — AWS S3 bronze layer with Hive-style date partitioning, credentials via GitHub OIDC rather than stored keys
- **Phase 4** — PySpark silver and gold layers (location normalisation, duplicate collapsing, expiry tracking)
- **Phase 5** — Flask REST API over the serving layer
- **Phase 6** — HTML + CSS dashboard, server-rendered with Jinja2
- **Phase 7** — RAG career advisor: `pgvector` embeddings over job descriptions, hybrid semantic + structured retrieval, skill-gap analysis
- **Phase 8** — Interview intelligence: recent interview experiences from public sources, joined to the existing `companies` and `skills` tables
