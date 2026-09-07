"""
Every SQL query the dashboard needs, in one place.

Each function takes a connection and returns plain Python data, so the
templates never contain SQL and the queries can be tested on their own.
"""

from psycopg2.extras import RealDictCursor


def _rows(conn, sql, params=None):
    """Run a query and return the rows as a list of dicts."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _one(conn, sql, params=None):
    """Run a query expected to return a single row."""
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


# ---------------------------------------------------------------
# Overview
# ---------------------------------------------------------------

def get_kpis(conn):
    return _one(conn, """
        SELECT
            (SELECT COUNT(*) FROM jobs)                        AS total_jobs,
            (SELECT COUNT(*) FROM companies)                   AS total_companies,
            (SELECT COUNT(*) FROM skills)                      AS total_skills,
            (SELECT COUNT(DISTINCT search_role) FROM jobs)     AS total_roles,
            (SELECT COUNT(*) FROM jobs WHERE salary_min IS NOT NULL)
                                                               AS jobs_with_salary
    """)


def get_last_run(conn):
    """The most recent successful pipeline run, for the 'last updated' line."""
    return _one(conn, """
        SELECT run_id, finished_at, jobs_fetched, jobs_inserted, jobs_updated
        FROM pipeline_runs
        WHERE status = 'success'
        ORDER BY run_id DESC
        LIMIT 1
    """)


# ---------------------------------------------------------------
# Skills
# ---------------------------------------------------------------

def get_top_skills(conn, limit=20):
    return _rows(conn, """
        SELECT s.skill_name, COUNT(*) AS job_count
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        GROUP BY s.skill_name
        ORDER BY job_count DESC
        LIMIT %s
    """, (limit,))


def get_skill_pairs(conn, limit=15):
    """
    Which two skills appear together most often in one posting.
    Self-join on job_skills; skill_id < skill_id drops self-pairs and
    mirrored duplicates.
    """
    return _rows(conn, """
        SELECT s1.skill_name AS skill_1,
               s2.skill_name AS skill_2,
               COUNT(*) AS pair_count
        FROM job_skills js1
        JOIN job_skills js2
          ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
        JOIN skills s1 ON js1.skill_id = s1.skill_id
        JOIN skills s2 ON js2.skill_id = s2.skill_id
        GROUP BY s1.skill_name, s2.skill_name
        ORDER BY pair_count DESC
        LIMIT %s
    """, (limit,))


# ---------------------------------------------------------------
# Salary
#
# Every salary figure carries the number of postings it is based on.
# Only about a third of listings disclose salary, so an average without
# its sample size is misleading.
# ---------------------------------------------------------------

def get_salary_by_role(conn, min_samples=10):
    return _rows(conn, """
        SELECT search_role,
               COUNT(*) FILTER (WHERE salary_min IS NOT NULL) AS with_salary,
               COUNT(*) AS total_jobs,
               ROUND(AVG(salary_min)) AS avg_min,
               ROUND(AVG(salary_max)) AS avg_max
        FROM jobs
        WHERE search_role IS NOT NULL
        GROUP BY search_role
        HAVING COUNT(*) FILTER (WHERE salary_min IS NOT NULL) >= %s
        ORDER BY avg_max DESC NULLS LAST
    """, (min_samples,))


def get_salary_by_location(conn, limit=20, min_samples=10):
    return _rows(conn, """
        SELECT location,
               COUNT(*) FILTER (WHERE salary_min IS NOT NULL) AS with_salary,
               COUNT(*) AS total_jobs,
               ROUND(AVG(salary_min)) AS avg_min,
               ROUND(AVG(salary_max)) AS avg_max
        FROM jobs
        WHERE location IS NOT NULL AND location <> 'India'
        GROUP BY location
        HAVING COUNT(*) FILTER (WHERE salary_min IS NOT NULL) >= %s
        ORDER BY with_salary DESC
        LIMIT %s
    """, (min_samples, limit))


def get_salary_by_skill(conn, limit=20, min_samples=10):
    return _rows(conn, """
        SELECT s.skill_name,
               COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL) AS with_salary,
               COUNT(*) AS total_jobs,
               ROUND(AVG(j.salary_min)) AS avg_min,
               ROUND(AVG(j.salary_max)) AS avg_max
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        JOIN jobs j ON js.job_id = j.job_id
        GROUP BY s.skill_name
        HAVING COUNT(*) FILTER (WHERE j.salary_min IS NOT NULL) >= %s
        ORDER BY avg_max DESC NULLS LAST
        LIMIT %s
    """, (min_samples, limit))


# ---------------------------------------------------------------
# Locations and companies
# ---------------------------------------------------------------

def get_top_locations(conn, limit=20):
    """
    City rankings. 'India' is excluded: Adzuna returns the country name
    when the employer gave no city at all, so it would sit at the top of
    every chart while saying nothing. get_unspecified_location_count()
    reports how many those are.
    """
    return _rows(conn, """
        SELECT location, COUNT(*) AS job_count
        FROM jobs
        WHERE location IS NOT NULL AND location <> 'India'
        GROUP BY location
        ORDER BY job_count DESC
        LIMIT %s
    """, (limit,))


def get_unspecified_location_count(conn):
    """Postings whose location is just 'India' — no city given."""
    row = _one(conn, "SELECT COUNT(*) AS n FROM jobs WHERE location = 'India'")
    return row["n"] if row else 0


def get_top_companies(conn, limit=50):
    return _rows(conn, """
        SELECT c.name,
               COUNT(*) AS job_count,
               COUNT(DISTINCT j.search_role) AS role_count
        FROM jobs j
        JOIN companies c ON j.company_id = c.company_id
        GROUP BY c.name
        ORDER BY job_count DESC
        LIMIT %s
    """, (limit,))


# ---------------------------------------------------------------
# Per-role pages
# ---------------------------------------------------------------

def get_roles(conn):
    """Every search role with its job count — drives the 30 role pages."""
    return _rows(conn, """
        SELECT search_role, COUNT(*) AS job_count
        FROM jobs
        WHERE search_role IS NOT NULL
        GROUP BY search_role
        ORDER BY job_count DESC
    """)


def get_role_skills(conn, role, limit=15):
    return _rows(conn, """
        SELECT s.skill_name, COUNT(*) AS job_count
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        JOIN jobs j ON js.job_id = j.job_id
        WHERE j.search_role = %s
        GROUP BY s.skill_name
        ORDER BY job_count DESC
        LIMIT %s
    """, (role, limit))


def get_role_locations(conn, role, limit=10):
    return _rows(conn, """
        SELECT location, COUNT(*) AS job_count
        FROM jobs
        WHERE search_role = %s
          AND location IS NOT NULL
          AND location <> 'India'
        GROUP BY location
        ORDER BY job_count DESC
        LIMIT %s
    """, (role, limit))


def get_role_summary(conn, role):
    return _one(conn, """
        SELECT COUNT(*) AS total_jobs,
               COUNT(DISTINCT company_id) AS companies,
               COUNT(*) FILTER (WHERE salary_min IS NOT NULL) AS with_salary,
               ROUND(AVG(salary_min)) AS avg_min,
               ROUND(AVG(salary_max)) AS avg_max
        FROM jobs
        WHERE search_role = %s
    """, (role,))


def get_role_jobs(conn, role, limit=50):
    """Newest postings for a role, with the link back to the original ad."""
    return _rows(conn, """
        SELECT j.title, c.name AS company, j.location,
               j.salary_min, j.salary_max, j.posted_date, j.redirect_url
        FROM jobs j
        JOIN companies c ON j.company_id = c.company_id
        WHERE j.search_role = %s
        ORDER BY j.posted_date DESC NULLS LAST
        LIMIT %s
    """, (role, limit))
def get_categories(conn, limit=6):
    """Adzuna's own job categories — a genuine categorical split."""
    return _rows(conn, """
        SELECT category, COUNT(*) AS job_count
        FROM jobs
        WHERE category IS NOT NULL
        GROUP BY category
        ORDER BY job_count DESC
        LIMIT %s
    """, (limit,))
