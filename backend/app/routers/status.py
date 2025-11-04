from fastapi import APIRouter
from app.core.celery_app import celery_app
from sqlalchemy import text
from redis import Redis
import requests
from app.core.config import REDIS_URL, OLLAMA_BASE

router = APIRouter(prefix="/task", tags=["Task"])

@router.get("/status/{task_id}")
def task_status(task_id: str):
    res = celery_app.AsyncResult(task_id)
    return {"id": task_id, "state": res.state, "result": res.result if res.successful() else None}

@router.get("/health")
def health_check():
    out = {}

    # DB
    try:
        # db_service는 import 시점에 engine을 만든다(현재 구조).
        # 여기서는 간단한 ping만으로 충분: SELECT 1
        from app.services.db_service import engine
        if engine is None:
            out["database"] = "ERROR: engine is None (DB_URL missing?)"
        else:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            out["database"] = "OK"
    except Exception as e:
        out["database"] = f"ERROR: {e}"

    # Redis
    try:
        r = Redis.from_url(REDIS_URL)
        r.ping()
        out["redis"] = "OK"
    except Exception as e:
        out["redis"] = f"ERROR: {e}"

    # Ollama
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        out["ollama"] = "OK" if resp.status_code == 200 else f"ERROR: {resp.status_code}"
    except Exception as e:
        out["ollama"] = f"ERROR: {e}"

    return out

@router.get("/ollama/models")
def list_ollama_models():
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return resp.json() if resp.ok else {"error": f"status {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}