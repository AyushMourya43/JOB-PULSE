"""
Render the dashboard as static HTML.

Every page is generated ahead of time and served as a plain file, so the
site has no server to wake up, nothing to time out, and no runtime
dependency on the database. The scheduled pipeline regenerates it after
each run.

Each page is written twice — light at the site root, dark under dark/ —
so the theme toggle is a plain link and survives navigation without any
JavaScript to remember it.
"""

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config.settings import BASE_DIR
from src.load import get_connection
from src.report import queries as q

TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = BASE_DIR / "site"


# ---------------------------------------------------------------
# Formatting helpers, exposed to templates as filters
# ---------------------------------------------------------------

def format_inr(value):
    """1988112 -> '19.9L'. Indian salaries are read in lakhs, not millions."""
    if value is None:
        return "—"
    return f"{float(value) / 100_000:.1f}L"


def format_num(value):
    if value is None:
        return "—"
    return f"{int(value):,}"


def format_pct(part, whole):
    if not whole:
        return "—"
    return f"{part / whole * 100:.0f}%"


def slugify(text):
    return text.replace(" ", "-").lower()


def with_widths(rows, value_key):
    """
    Add a percentage to each row, scaled against the largest value in the
    set — used as bar width for horizontal charts and bar height for
    vertical ones. Bars are only comparable within one chart, so the
    scale is per chart rather than global.
    """
    if not rows:
        return rows

    largest = max(row[value_key] for row in rows)

    for row in rows:
        row["width"] = round(row[value_key] / largest * 100, 1) if largest else 0

    return rows


def donut_stops(rows, value_key):
    """
    Build the conic-gradient stop list for a donut, and tag each row with
    its colour slot and share. Slots are assigned in the fixed
    categorical order, so a category keeps its colour as counts move.
    """
    total = sum(row[value_key] for row in rows) or 1
    stops = []
    position = 0.0

    for index, row in enumerate(rows, start=1):
        share = row[value_key] / total * 100
        stops.append(f"var(--c{index}) {position:.3f}% {position + share:.3f}%")
        row["share"] = round(share, 1)
        row["slot"] = index
        position += share

    return ", ".join(stops)


def build_env():
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["inr"] = format_inr
    env.filters["num"] = format_num
    env.filters["slug"] = slugify
    env.globals["pct"] = format_pct
    return env


def render(env, template_name, output_name, quiet=False, **context):
    """
    Write the page twice: light at the site root, dark under dark/.
    The two copies differ only in the data-theme stamp and the paths to
    the stylesheet and the toggle.
    """
    template = env.get_template(template_name)

    variants = [
        (OUTPUT_DIR / output_name,          "light", "style.css",    f"dark/{output_name}"),
        (OUTPUT_DIR / "dark" / output_name, "dark",  "../style.css", f"../{output_name}"),
    ]

    for path, theme, css, toggle_href in variants:
        path.parent.mkdir(parents=True, exist_ok=True)
        html = template.render(theme=theme, css=css, toggle_href=toggle_href, **context)
        path.write_text(html, encoding="utf-8")

    if not quiet:
        print(f"  {output_name}")


# ---------------------------------------------------------------
# Pages
# ---------------------------------------------------------------

def build_overview(env, conn, shared):
    kpis = q.get_kpis(conn)

    disclosed = kpis["jobs_with_salary"]
    salary_split = [
        {"category": "States a salary", "job_count": disclosed},
        {"category": "No salary given", "job_count": kpis["total_jobs"] - disclosed},
    ]

    categories = q.get_categories(conn, 6)

    render(
        env, "index.html", "index.html",
        page="overview",
        kpis=kpis,
        top_skills=with_widths(q.get_top_skills(conn, 10), "job_count"),
        cities=with_widths(q.get_top_locations(conn, 8), "job_count"),
        top_companies=q.get_top_companies(conn, 8),
        unspecified=q.get_unspecified_location_count(conn),
        salary_split=salary_split,
        salary_stops=donut_stops(salary_split, "job_count"),
        salary_pct=format_pct(disclosed, kpis["total_jobs"]),
        categories=categories,
        category_stops=donut_stops(categories, "job_count"),
        **shared,
    )


def build_skills(env, conn, shared):
    render(
        env, "skills.html", "skills.html",
        page="skills",
        kpis=q.get_kpis(conn),
        top_skills=with_widths(q.get_top_skills(conn, 25), "job_count"),
        pairs=q.get_skill_pairs(conn, 15),
        **shared,
    )


def build_salary(env, conn, shared):
    render(
        env, "salary.html", "salary.html",
        page="salary",
        kpis=q.get_kpis(conn),
        by_role=q.get_salary_by_role(conn),
        by_skill=q.get_salary_by_skill(conn, 20),
        by_location=q.get_salary_by_location(conn, 20),
        **shared,
    )


def build_locations(env, conn, shared):
    render(
        env, "locations.html", "locations.html",
        page="locations",
        kpis=q.get_kpis(conn),
        locations=with_widths(q.get_top_locations(conn, 20), "job_count"),
        by_location=q.get_salary_by_location(conn, 15),
        unspecified=q.get_unspecified_location_count(conn),
        **shared,
    )


def build_companies(env, conn, shared):
    render(
        env, "companies.html", "companies.html",
        page="companies",
        kpis=q.get_kpis(conn),
        companies=q.get_top_companies(conn, 50),
        **shared,
    )


def build_roles(env, conn, shared):
    roles = q.get_roles(conn)

    render(env, "roles.html", "roles.html", page="roles", roles=roles, **shared)

    for row in roles:
        role = row["search_role"]
        render(
            env, "role.html", f"role-{slugify(role)}.html",
            quiet=True,
            page="roles",
            role=role,
            summary=q.get_role_summary(conn, role),
            skills=with_widths(q.get_role_skills(conn, role, 12), "job_count"),
            locations=with_widths(q.get_role_locations(conn, role, 8), "job_count"),
            jobs=q.get_role_jobs(conn, role, 40),
            **shared,
        )

    print(f"  role-*.html ({len(roles)} pages)")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    env = build_env()
    conn = get_connection()

    try:
        # Values every page needs
        shared = {"last_run": q.get_last_run(conn)}

        print("building:")
        build_overview(env, conn, shared)
        build_skills(env, conn, shared)
        build_salary(env, conn, shared)
        build_locations(env, conn, shared)
        build_companies(env, conn, shared)
        build_roles(env, conn, shared)
    finally:
        conn.close()

    shutil.copy(STATIC_DIR / "style.css", OUTPUT_DIR / "style.css")
    print(f"  style.css\n\nwritten to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
