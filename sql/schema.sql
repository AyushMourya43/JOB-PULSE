CREATE TABLE companies (
    company_id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    location VARCHAR(255)
);

CREATE TABLE skills (
    skill_id SERIAL PRIMARY KEY,
    skill_name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE jobs (
    job_id SERIAL PRIMARY KEY,

    -- Adzuna's unique job ID
    external_id VARCHAR(100) UNIQUE NOT NULL,

    title VARCHAR(255) NOT NULL,

    -- Adzuna truncates every description at 500 characters
    description TEXT,

    -- Link to the original posting (powers the "Apply" button)
    redirect_url TEXT,

    company_id INTEGER REFERENCES companies(company_id),

    location VARCHAR(255),

    salary_min NUMERIC,
    salary_max NUMERIC,

    -- TRUE = Adzuna's own estimate, not employer-confirmed
    salary_is_predicted BOOLEAN,

    posted_date DATE,

    -- full_time / part_time
    contract_time VARCHAR(20),

    -- Adzuna category label, e.g. "IT Jobs"
    category VARCHAR(100),

    -- Which search term found this job
    search_role VARCHAR(100),

    source VARCHAR(50) DEFAULT 'adzuna',

    -- When our pipeline fetched this job
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- When this database record was last changed
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Used later for change detection
    job_hash VARCHAR(64)
);

CREATE TABLE job_skills (
    job_id INTEGER REFERENCES jobs(job_id),
    skill_id INTEGER REFERENCES skills(skill_id),

    PRIMARY KEY (job_id, skill_id)
);

-- Pipeline execution history
CREATE TABLE pipeline_runs (
    run_id SERIAL PRIMARY KEY,

    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,

    status VARCHAR(20),

    jobs_fetched INTEGER DEFAULT 0,
    jobs_inserted INTEGER DEFAULT 0,
    jobs_updated INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0
);
