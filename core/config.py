import os
import logging
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fresa_api")

AWS_KEY = os.getenv("AWS_KEY")
AWS_SECRET = os.getenv("AWS_SECRET")
REGION = os.getenv("REGION")
BUCKET = os.getenv("BUCKET")

SHARED_SECRET_KEY = os.getenv("SHARED_SECRET_KEY")

API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")

APP_TITLE = os.getenv("APP_TITLE")
APP_VERSION = os.getenv("APP_VERSION")
APP_DESC = os.getenv("APP_DESC")

ALLOWED_EXTENSIONS = {'msg', 'eml'}

LOGS_DIR = BASE_DIR / "logs"
CERT_DIR = BASE_DIR / "certs"
BACKUP_DIR = BASE_DIR / "backup"

for directory in [LOGS_DIR, CERT_DIR, BACKUP_DIR]:
    os.makedirs(directory, exist_ok=True)

try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
    logger.warning("EasyOCR not found. Visiting card OCR might be limited.")

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("Pytesseract not found.")

if not AWS_KEY or not AWS_SECRET or not BUCKET:
    logger.warning("CRITICAL: AWS Credentials or Bucket not set in .env file!")

if not SHARED_SECRET_KEY:
    logger.warning("WARNING: SHARED_SECRET_KEY not set. Email sending will fail.")