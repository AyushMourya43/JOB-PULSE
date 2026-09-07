import json
import logging
import time
from datetime import datetime, timezone
import requests
from src import logger
from config.settings import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ADZUNA_BASE_URL,
    RAW_DATA_DIR,
    REQUEST_TIMEOUT,
)

MAX_RETRIES = 3
RETRY_DELAY = 5

# Adzuna allows 25 hits/min, so pace the requests
RATE_LIMIT_DELAY = 1.5

# Transient failures worth retrying. 429 is included because Adzuna's
# limit is per minute — waiting is exactly the right response.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def fetch_page(session, url, params, page):
    """
    Fetch a single page, retrying transient failures.

    Returns the list of results for the page, or None if the page could
    not be fetched. An empty list is a valid answer: it means the search
    has no more results.
    """

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json().get("results", [])

        except requests.exceptions.HTTPError as error:
            status = error.response.status_code if error.response is not None else None

            if status in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                logging.warning(
                    f"Page {page}: server returned {status}. "
                    f"Retry {attempt}/{MAX_RETRIES} in {RETRY_DELAY}s..."
                )
                time.sleep(RETRY_DELAY)
                continue

            # 401, 404 and friends will not fix themselves — stop trying
            logging.error(f"Page {page}: HTTP {status}. Giving up on this page.")
            return None

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as error:

            if attempt < MAX_RETRIES:
                logging.warning(
                    f"Page {page}: {type(error).__name__}. "
                    f"Retry {attempt}/{MAX_RETRIES} in {RETRY_DELAY}s..."
                )
                time.sleep(RETRY_DELAY)
                continue

            logging.error(f"Page {page}: {type(error).__name__}. Giving up on this page.")
            return None

        except requests.exceptions.RequestException as error:
            logging.error(f"Page {page}: {error}")
            return None

    return None


def fetch_jobs(what, where="", country="in", results_per_page=50,
               max_pages=5, sort_by="date"):
    """
    Fetch postings for one search term.

    sort_by defaults to "date" so the first pages hold the newest
    postings. The daily run only reads a few pages, and with Adzuna's
    default relevance ordering those pages would return the same
    long-standing listings every day while new postings — further down
    the list — were never seen at all.
    """

    logging.info(f"Fetching jobs for '{what}' (sorted by {sort_by})...")

    all_results = []
    session = requests.Session()

    try:
        for page in range(1, max_pages + 1):

            url = f"{ADZUNA_BASE_URL}/{country}/search/{page}"

            # exactly what we need from the API
            params = {
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": what,
                "where": where,
                "results_per_page": results_per_page,
                "sort_by": sort_by,
                "content-type": "application/json",
            }

            page_results = fetch_page(session, url, params, page)

            # A failed page ends the fetch, but everything already
            # collected is kept — partial data beats no data.
            if page_results is None:
                logging.warning(
                    f"Page {page} failed. Keeping the {len(all_results)} "
                    f"jobs collected so far."
                )
                break

            # The search is exhausted. Requesting the remaining pages
            # would burn API quota for nothing.
            if not page_results:
                logging.info(f"Page {page}: no more results, stopping.")
                break

            logging.info(f"Page {page}: fetched {len(page_results)} jobs")
            all_results.extend(page_results)

            # No need to wait after the final request
            if page < max_pages:
                time.sleep(RATE_LIMIT_DELAY)

    finally:
        session.close()

    if not all_results:
        logging.error(f"No jobs fetched for '{what}'.")
        return None

    logging.info(f"Data fetched successfully — {len(all_results)} total jobs.")

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_query = what.replace(" ", "_").lower()

    # One payload object, written to disk and returned, so the file
    # and the return value can never drift apart
    payload = {
        "search_role": what,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sort_by": sort_by,
        "results": all_results,
    }

    with open(
        RAW_DATA_DIR / f"jobs_raw_{safe_query}.json", "w", encoding="utf-8") as file:

        json.dump(payload, file, indent=2, ensure_ascii=False)

    return payload
