from pathlib import Path
import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

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

def _assemble_db_url_if_missing():
    global DB_URL
    if DB_URL:
        return
    u = os.getenv("DB_USER")
    p = os.getenv("DB_PASS")
    h = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    n = os.getenv("DB_NAME")
    if all([u, p, h, port, n]):
        # pymysql 사용, utf8mb4 고정
        DB_URL = f"mysql+pymysql://{u}:{p}@{h}:{port}/{n}?charset=utf8mb4"

_assemble_db_url_if_missing()

class Settings(BaseSettings):
    DB_USER: str | None = None
    DB_PASS: str | None = None
    DB_HOST: str | None = None
    DB_PORT: str | None = None
    DB_NAME: str | None = None
    DB_URL: str | None = None

    REDIS_URL: str = "redis://localhost:6379/0"
    OLLAMA_BASE: str = "http://127.0.0.1:11434"
    LLM_MODEL: str = "gemma3-summarizer"

    def assemble_db_url(self) -> str:
        if self.DB_URL:
            return self.DB_URL
        if all([self.DB_USER, self.DB_PASS, self.DB_HOST, self.DB_PORT, self.DB_NAME]):
            return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        raise ValueError("DB connection info incomplete: please set .env properly")

settings = Settings()

# ✅ 여기가 핵심: Celery에서 import할 수 있도록 전역 변수 선언
DATABASE_URL = settings.assemble_db_url()
REDIS_URL = settings.REDIS_URL
OLLAMA_BASE = settings.OLLAMA_BASE