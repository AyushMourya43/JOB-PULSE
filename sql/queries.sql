-- Query 1: Top 10 skills overall (across every role)
-- Joins job_skills to skills to turn skill_id into the actual skill name,
-- then counts how many jobs mention each skill so the most in-demand ones
-- come first. (FR4 — "Top N skills overall")
SELECT s.skill_name, COUNT(*) AS job_count
FROM job_skills js
JOIN skills s ON js.skill_id = s.skill_id
GROUP BY s.skill_name
ORDER BY job_count DESC
LIMIT 10;

-- Query 2: Top 10 skills for one specific role (here "Data Engineer")
-- Same shape as Query 1, plus one extra JOIN (to the jobs table) and a
-- WHERE filter so only that role's jobs are counted.
-- (FR4 — "Top N skills by role")
SELECT s.skill_name, COUNT(*) AS job_count
FROM job_skills js
JOIN skills s ON js.skill_id = s.skill_id
JOIN jobs j ON js.job_id = j.job_id
WHERE j.title ILIKE '%data engineer%'
GROUP BY s.skill_name
ORDER BY job_count DESC
LIMIT 10;

-- Query 3: Average salary by location
-- The WHERE salary_min IS NOT NULL filter is required because many postings
-- have no salary data at all — without it the averages would be computed
-- over a mix of real and missing values. This returns only locations that
-- have at least some salary data.
-- (FR4 — "Average/min/max salary by location")
SELECT location,
       COUNT(*) AS job_count,
       ROUND(AVG(salary_min)) AS avg_salary_min,
       ROUND(AVG(salary_max)) AS avg_salary_max
FROM jobs
WHERE salary_min IS NOT NULL
GROUP BY location
ORDER BY job_count DESC
LIMIT 10;

-- Query 4: Skill co-occurrence — which two skills appear together most often
-- in the same job posting. Uses a self-join on job_skills: matching on
-- job_id pairs up the skills of the same job, and the skill_id < skill_id
-- condition removes self-pairs and mirrored duplicates.
-- (FR4 — "Skills that most often appear together in the same posting")
SELECT s1.skill_name AS skill_1, s2.skill_name AS skill_2, COUNT(*) AS pair_count
FROM job_skills js1
JOIN job_skills js2 ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
JOIN skills s1 ON js1.skill_id = s1.skill_id
JOIN skills s2 ON js2.skill_id = s2.skill_id
GROUP BY s1.skill_name, s2.skill_name
ORDER BY pair_count DESC
LIMIT 10;

-- Flat export used to build the CSV (one row per job-skill pair, plus one
-- row for jobs that matched no skill).
SELECT
    j.job_id,
    j.title,
    c.name AS company,
    j.location,
    j.salary_min,
    j.salary_max,
    j.posted_date,
    j.source,
    s.skill_name
FROM jobs j
JOIN companies c ON j.company_id = c.company_id
LEFT JOIN job_skills js ON j.job_id = js.job_id
LEFT JOIN skills s ON js.skill_id = s.skill_id;
