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

ALLOWED_EXTENSIONS = {'msg', 'eml'}

LOGS_DIR = BASE_DIR / "logs"
CERT_DIR = BASE_DIR / "cert"
BACKUP_DIR = BASE_DIR / "backup"
OUTPUT_DIR = BASE_DIR / "ouput"

for directory in [LOGS_DIR, CERT_DIR, BACKUP_DIR, OUTPUT_DIR]:
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