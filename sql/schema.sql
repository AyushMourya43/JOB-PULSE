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
    external_id VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    company_id INTEGER REFERENCES companies(company_id),
    location VARCHAR(255),
    salary_min NUMERIC,
    salary_max NUMERIC,
    posted_date DATE,
    source VARCHAR(50)
);

CREATE TABLE job_skills (
    job_id INTEGER REFERENCES jobs(job_id),
    skill_id INTEGER REFERENCES skills(skill_id),
    PRIMARY KEY (job_id, skill_id)
);

