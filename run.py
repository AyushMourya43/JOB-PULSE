"""
JobPulse pipeline entry point.

Fetches job postings from Adzuna, cleans them, and loads them into
PostgreSQL as a single tracked pipeline run.
"""

import argparse
import json
import logging

from src import logger
from src.extract import fetch_jobs
from src.transform import clean_jobs
from src.load import get_connection, run_pipeline
from config.settings import BASE_DIR, RAW_DATA_DIR, check_config

SEARCH_TERMS_FILE = BASE_DIR / "config" / "search_terms.json"


def load_search_terms(groups=None):
    """Read search terms from config, optionally limited to some groups."""

    with open(SEARCH_TERMS_FILE, encoding="utf-8") as file:
        data = json.load(file)

    if groups:
        unknown = [g for g in groups if g not in data]
        if unknown:
            raise SystemExit(
                f"Unknown group(s): {', '.join(unknown)}. "
                f"Available: {', '.join(data)}"
            )
        selected = groups
    else:
        selected = list(data)

    return [term for group in selected for term in data[group]]


def raw_path(term):
    """Where fetch_jobs() writes the raw response for this search term."""
    return RAW_DATA_DIR / f"jobs_raw_{term.replace(' ', '_').lower()}.json"


def fetch_and_clean(terms, max_pages):
    """Yield (term, DataFrame), calling the Adzuna API for each term."""

    for term in terms:

        data = fetch_jobs(what=term, max_pages=max_pages)

        if data is None:
            # fetch_jobs already logged the reason. One failed role should
            # not abort the whole run.
            logging.error(f"{term} -> fetch failed, skipping")
            continue

        yield term, clean_jobs(raw_path(term))


def clean_only(terms):
    """Yield (term, DataFrame) from raw files already on disk — no API calls."""

    for term in terms:

        path = raw_path(term)

        if not path.exists():
            logging.warning(f"{term} -> no raw file at {path.name}, skipping")
            continue

        yield term, clean_jobs(path)


def parse_args(argv=None):

    parser = argparse.ArgumentParser(
        description="Run the JobPulse ingestion pipeline."
    )

    parser.add_argument(
        "--roles",
        nargs="+",
        metavar="ROLE",
        help="Only run these search terms (default: every term in search_terms.json)"
    )

    parser.add_argument(
        "--groups",
        nargs="+",
        metavar="GROUP",
        help="Only run these groups from search_terms.json, e.g. tech"
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=5,
        help="Adzuna pages per role, 50 results each. "
             "Lower this to stay inside the API quota (default: 8)"
    )

    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Skip the API entirely and load the raw files already on disk"
    )

    return parser.parse_args(argv)


def main(argv=None):

    args = parse_args(argv)

    # Fail before doing any work, and only demand the credentials this
    # particular run actually needs.
    check_config(need_api=not args.skip_fetch, need_db=True)

    terms = args.roles if args.roles else load_search_terms(args.groups)

    if not terms:
        raise SystemExit("No search terms selected.")

    # Show the API cost up front — this is the number that has to stay
    # inside the Adzuna quota.
    api_calls = 0 if args.skip_fetch else len(terms) * args.max_pages

    message = f"{len(terms)} role(s), up to {api_calls} Adzuna API calls."
    logging.info(message)
    print(message)

    dataframes = (
        clean_only(terms)
        if args.skip_fetch
        else fetch_and_clean(terms, args.max_pages)
    )

    conn = get_connection()

    try:
        totals = run_pipeline(conn, dataframes)
    finally:
        # Always closed, even if the run raised
        conn.close()

    print(
        f"Done — {totals['inserted']} inserted, {totals['updated']} updated, "
        f"{totals['unchanged']} unchanged, {totals['skipped']} skipped."
    )


if __name__ == "__main__":
    main()
