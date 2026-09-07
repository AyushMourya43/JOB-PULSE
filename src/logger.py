import logging
import sys
from datetime import date
from config.settings import LOGS_DIR

log_format = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
today = str(date.today())

LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Log to a daily file AND to stdout. The file is for reading afterwards;
# stdout is what GitHub Actions, Render and Docker actually capture — a
# log that only exists inside the container is a log nobody will read.
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True,
    handlers=[
        logging.FileHandler(f"{LOGS_DIR}/{today}_app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
