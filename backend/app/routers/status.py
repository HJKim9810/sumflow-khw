from fastapi import APIRouter
from ..core.celery_app import celery_app

router = APIRouter(prefix="/task", tags=["Task"])

@router.get("/status/{task_id}")
def task_status(task_id: str):
    res = celery_app.AsyncResult(task_id)
    return {"id": task_id, "state": res.state, "result": res.result if res.successful() else None}