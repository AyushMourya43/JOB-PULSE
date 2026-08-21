import logging
from datetime import date
from config.settings import LOGS_DIR

log_format = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
today = str(date.today())

LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=f"{LOGS_DIR}/{today}_app.log",
    level=logging.INFO,
    format=log_format,
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True
)