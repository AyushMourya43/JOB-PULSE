from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
LOGS_DIR = BASE_DIR / "logs"


def _get(name, default=None):
    """Read an env var, treating an empty string the same as unset."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _get_int(name, default):
    """Read an integer env var, failing with a message that names the variable."""
    raw = _get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a whole number, got {raw!r}")


# ---------------------------------------------------------------
# Adzuna API
# ---------------------------------------------------------------

ADZUNA_BASE_URL = _get("ADZUNA_BASE_URL", "https://api.adzuna.com/v1/api/jobs")
ADZUNA_APP_ID = _get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = _get("ADZUNA_APP_KEY")
REQUEST_TIMEOUT = _get_int("REQUEST_TIMEOUT", 30)

# ---------------------------------------------------------------
# PostgreSQL
#
# sslmode matters once the database is not local: Neon and Supabase both
# require SSL, while a local server usually has it disabled. Keeping it
# in the environment means moving to a hosted database is a config
# change, not a code change.
# ---------------------------------------------------------------

DB_HOST = _get("DB_HOST", "localhost")
DB_PORT = _get_int("DB_PORT", 5432)
DB_NAME = _get("DB_NAME", "jobpulse")
DB_USER = _get("DB_USER")
DB_PASSWORD = _get("DB_PASSWORD")
DB_SSLMODE = _get("DB_SSLMODE", "prefer")


def check_config(need_api=True, need_db=True):
    """
    Fail early, with a message that says exactly what is missing.

    Called from the entry point rather than at import time, so that
    --help and the test suite still work without a fully populated .env.
    """

    missing = []

    if need_api:
        if not ADZUNA_APP_ID:
            missing.append("ADZUNA_APP_ID")
        if not ADZUNA_APP_KEY:
            missing.append("ADZUNA_APP_KEY")

    if need_db:
        if not DB_USER:
            missing.append("DB_USER")

    if missing:
        raise SystemExit(
            "Missing required configuration: " + ", ".join(missing) + "\n"
            f"Set them in {BASE_DIR / '.env'} — see .env.example for the full list."
        )
