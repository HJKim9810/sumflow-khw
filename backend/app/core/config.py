from pathlib import Path
import os
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parents[1]
load_dotenv(BASE.parent / ".env")

APP_ENV = os.getenv("APP_ENV", "dev")

OUTPUT_ROOT = (BASE / os.getenv("OUTPUT_ROOT", "ocr_store")).resolve()
EXPORT_ROOT = (BASE / os.getenv("EXPORT_ROOT", "exports")).resolve()
for d in (OUTPUT_ROOT, EXPORT_ROOT):
    d.mkdir(parents=True, exist_ok=True)

TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
TESSDATA_PREFIX = os.getenv("TESSDATA_PREFIX", "")

OCR_DPI = int(os.getenv("OCR_DPI", 300))
OCR_LANGS = os.getenv("OCR_LANGS", "kor+eng")
OCR_PSM = int(os.getenv("OCR_PSM", 6))
OCR_PREP_MODE = os.getenv("OCR_PREP_MODE", "sauvola")

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma3-summarizer")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DB_URL = os.getenv("DB_URL")