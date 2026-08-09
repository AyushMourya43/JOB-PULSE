# JobPulse — Job Market Skill & Salary Analytics

**Version 1.0**

A data pipeline that pulls live job postings from the Adzuna API, cleans and structures the data with pandas, stores it in a normalized PostgreSQL database, and visualizes it in an interactive Tableau Public dashboard — showing which technical and non-technical skills are in demand, how they cluster together, and what salaries look like across roles and locations in the Indian job market.

**Live Dashboard:** https://public.tableau.com/app/profile/ayush.mourya/viz/JobPulse-JobMarketSkillSalaryAnalytics/Dashboard1

---

## What It Does

- Fetches job postings for 30 different roles (20 tech + 10 non-tech) from the Adzuna API, with pagination, retries, and rate limiting
- Cleans the raw data: removes duplicates, normalizes salary fields, extracts skills from job descriptions using a curated skill list
- Loads the cleaned data into a normalized PostgreSQL schema (`companies`, `jobs`, `skills`, `job_skills`)
- Answers analysis questions with SQL: top in-demand skills, salary trends by location, skills that most often appear together
- Presents the findings in a 6-chart Tableau Public dashboard with interactive filters

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.14 |
| Data collection | `requests`, Adzuna API |
| Data manipulation | `pandas` |
| Database | PostgreSQL |
| DB access | `psycopg2` |
| Config | `python-dotenv` |
| Analysis | SQL (joins, GROUP BY, self-joins) |
| Dashboard | Tableau Public |
| Testing | `pytest` (planned for v1.1) |

## What's New Here (Things I Learned Building This)

This project builds on an earlier ETL project (a crypto price tracker) and pushed into new territory:

- **Connecting to PostgreSQL from Python** using `psycopg2` — writing idempotent `INSERT ... ON CONFLICT DO NOTHING` upsert logic so re-running the pipeline never creates duplicate rows
- **Designing a normalized relational schema** from scratch — a `job_skills` junction table to model the many-to-many relationship between jobs and skills, instead of storing skills as a messy comma-separated string
- **Rule-based skill extraction from free text**, and fixing a real bug along the way: naive substring matching caused false positives (e.g. "Scala" was matching inside the word "escalation"). Fixed by switching to regex word-boundary matching (`\bscala\b`)
- **API resilience** — pagination across multiple pages, exponential-style retry on server errors, and rate limiting to stay within Adzuna's request limits
- **SQL analysis at scale** — joins, GROUP BY/HAVING, and a self-join on the `job_skills` table to compute skill co-occurrence pairs
- **Building a multi-chart Tableau dashboard** — bar charts, a skill×location heatmap, a donut chart, a packed bubble chart, combined into one dashboard with cross-filtering

## Data Volume

- **30 roles** fetched (20 tech + 10 non-tech), up to 400 postings each (8 paginated API calls per role, 50 results/page)
- **30 raw JSON files**, ~11,800 lines / ~600 KB each — **354,044 lines of raw JSON** processed in total
- After cleaning and deduplication: **11,334 unique jobs** loaded across **5,499 unique companies**
- **47 distinct skills** tracked, forming **10,848 job-skill relationships** in the `job_skills` table
- Final flat export for Tableau: **14,321 rows** (one row per job-skill pair, plus one row for jobs with no matched skill)

## Data Quality Notes (Read Before Trusting the Numbers)

Real job market data is messy. This project surfaces that honestly rather than hiding it:

- **Salary coverage is ~38%** of postings — many Indian job listings don't disclose salary. Salary averages are based only on the subset of postings that included this data, not the full dataset.
- **Skill extraction depends on the description text Adzuna returns**, which is sometimes truncated. Jobs with short/truncated descriptions may show fewer matched skills than they actually require.
- **~500 postings had no company name** — mostly recruitment/staffing agency listings that don't disclose the hiring company ("blind postings"). These were excluded during load rather than loaded with a fake company name.
- Some salary figures from Adzuna are flagged as `salary_is_predicted` (Adzuna's own estimate, not always employer-confirmed) — this flag is not currently tracked in the schema.

## Project Structure

```
job-pulse/
├── config/
│   └── settings.py       # loads .env, central config
├── src/
│   ├── logger.py          # logging setup (imported for side effects)
│   ├── extract.py         # Adzuna API fetch, pagination, retries
│   ├── transform.py       # cleaning, dedup, salary normalization, skill extraction
│   └── load.py             # psycopg2 inserts into Postgres, dedup-safe
├── sql/
│   ├── schema.sql          # table definitions (companies, jobs, skills, job_skills)
│   └── queries.sql         # analysis queries (top skills, salary, co-occurrence)
├── data/
│   ├── raw/                 # raw API responses (gitignored)
│   └── processed/           # exported CSV for Tableau (gitignored)
├── logs/                    # daily log files (gitignored)
├── run.py                   # pipeline entry point (extract → transform → load, all 30 roles)
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
5. Run the full pipeline:
   ```bash
   python run.py
   ```
6. Export the data for Tableau:
   ```bash
   psql -d jobpulse -c "\copy (SELECT j.job_id, j.title, c.name AS company, j.location, j.salary_min, j.salary_max, j.posted_date, j.source, s.skill_name FROM jobs j JOIN companies c ON j.company_id = c.company_id LEFT JOIN job_skills js ON j.job_id = js.job_id LEFT JOIN skills s ON js.skill_id = s.skill_id) TO 'data/processed/jobs_export.csv' WITH CSV HEADER"
   ```
7. Open the CSV in Tableau Public Desktop to rebuild or refresh the dashboard.

## Roadmap

- **v1.0 (current)** — local ETL pipeline, normalized Postgres schema, SQL analysis, published Tableau dashboard
- **Tier 2 (planned)** — GitHub Actions to run the pipeline on a schedule, data quality checks, containerization
