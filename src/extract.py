import json
import logging
import time
import requests
from src import logger
from config.settings import (
    ADZUNA_APP_ID,
    ADZUNA_APP_KEY,
    ADZUNA_BASE_URL,
    RAW_DATA_DIR,
    REQUEST_TIMEOUT,
)


def fetch_jobs(what, where="", country="in", results_per_page=50, max_pages=8):

    logging.info(f"Fetching jobs for '{what}'...\n")

    all_results = []

    session = requests.Session()

    try:
        for page in range(1, max_pages + 1):
            url = f"{ADZUNA_BASE_URL}/{country}/search/{page}"

            # what exaclty i need from the api
            params = {
                "app_id": ADZUNA_APP_ID,
                "app_key": ADZUNA_APP_KEY,
                "what": what,
                "where": where,
                "results_per_page": results_per_page,
                "content-type": "application/json",
            }

            retry = 0

            while retry < 3:

                try:

                    response = session.get(
                        url,
                        params=params,
                        timeout=REQUEST_TIMEOUT
                    )

                    response.raise_for_status()

                    page_results = response.json().get("results", [])

                    if not page_results:
                        logging.info(f"Page {page}: no more results, stopping.")
                        break

                    logging.info(f"Page {page}: fetched {len(page_results)} jobs")
                    all_results.extend(page_results)

                    break

                except requests.exceptions.HTTPError as error:

                    if response.status_code in [500, 502, 503, 504]:

                        retry += 1

                        logging.warning(
                            f"Server busy (Status {response.status_code}). Retry {retry}/3 after 5 seconds..."
                        )

                        time.sleep(5)

                    else:
                        raise error

            if retry == 3:
                logging.error(f"Skipping page {page} after 3 failed retries.")
                continue

            time.sleep(1.5)   # rate limit (25 hits/min) s

        logging.info(f"Data fetched successfully — {len(all_results)} total jobs.\n")

        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        safe_query = what.replace(" ", "_").lower()

        with open(
            RAW_DATA_DIR / f"jobs_raw_{safe_query}.json", "w",encoding="utf-8") as file:

            json.dump({"results": all_results}, file,indent=2,ensure_ascii=False)

        return {"results": all_results}

    except requests.exceptions.Timeout:
        logging.error("Request timed out.")

    except requests.exceptions.ConnectionError:
        logging.error("Internet connection error.")

    except requests.exceptions.HTTPError as error:
        logging.error(f"HTTP Error: {error}")

    except requests.exceptions.RequestException as error:
        logging.error(f"Something went wrong: {error}")

    return None