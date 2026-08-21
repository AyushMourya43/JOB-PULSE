-- Query 1: Top 10 skills overall (saare roles milaake)
-- job_skills ko skills se JOIN karke skill_id ki jagah asli naam nikala,
-- phir har skill kitni jobs mein hai wo count karke sabse zyada demand
-- wali skills upar dikhayi (FR4 — "Top N skills overall")
SELECT s.skill_name, COUNT(*) AS job_count
FROM job_skills js
JOIN skills s ON js.skill_id = s.skill_id
GROUP BY s.skill_name
ORDER BY job_count DESC
LIMIT 10;

-- Query 2: Top 10 skills sirf ek specific role ke liye (yaha "Data Engineer")
-- Query 1 jaisi hi hai, bas ek extra JOIN (jobs table se) aur WHERE filter
-- add kiya taaki sirf us role ki jobs ka data count ho
-- (FR4 — "Top N skills by role")
SELECT s.skill_name, COUNT(*) AS job_count
FROM job_skills js
JOIN skills s ON js.skill_id = s.skill_id
JOIN jobs j ON js.job_id = j.job_id
WHERE j.title ILIKE '%data engineer%'
GROUP BY s.skill_name
ORDER BY job_count DESC
LIMIT 10;

-- Query 3: Location ke hisaab se average salary
-- WHERE salary_min IS NOT NULL zaroori hai kyunki kaafi jobs mein salary
-- data hi missing hai — isse sirf wahi locations dikhengi jaha kam se kam
-- kuch salary data available hai (FR4 — "Average/min/max salary by location")
SELECT location,
       COUNT(*) AS job_count,
       ROUND(AVG(salary_min)) AS avg_salary_min,
       ROUND(AVG(salary_max)) AS avg_salary_max
FROM jobs
WHERE salary_min IS NOT NULL
GROUP BY location
ORDER BY job_count DESC
LIMIT 10;

-- Query 4: Skill co-occurrence — kaunsi do skills sabse zyada saath mein
-- (same job posting mein) aati hain. Self-join use kiya job_skills table
-- pe — job_id match karke same job ki skill-pairs nikali, aur
-- skill_id < skill_id condition se duplicate/self-pairs hatai
-- (FR4 — "Skills that most often appear together in the same posting")
SELECT s1.skill_name AS skill_1, s2.skill_name AS skill_2, COUNT(*) AS pair_count
FROM job_skills js1
JOIN job_skills js2 ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
JOIN skills s1 ON js1.skill_id = s1.skill_id
JOIN skills s2 ON js2.skill_id = s2.skill_id
GROUP BY s1.skill_name, s2.skill_name
ORDER BY pair_count DESC
LIMIT 10;
 

-- this is csv data  
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
