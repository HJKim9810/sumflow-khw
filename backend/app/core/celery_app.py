import os
from celery import Celery
from kombu import Queue
from .config import REDIS_URL  # REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery 인스턴스 생성
# include=["app.tasks"] 로 tasks 모듈을 명시적으로 로드 (autodiscover 대체)
celery_app = Celery(
    "sumflow",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

# 기본 설정
celery_app.conf.update(
    # 타임존/UTC
    timezone="Asia/Seoul",
    enable_utc=False,

    # 결과 보존/상태 추적
    task_track_started=True,
    result_expires=3600 * 12,  # 12시간

    # 라우팅: 태스크 이름 -> 큐
    task_routes={
        "tasks.ocr_cpu": {"queue": "ocr_cpu"},
        "tasks.llm_gpu": {"queue": "llm_gpu"},
        "tasks.postproc": {"queue": "postproc"},
    },

    # 안전한 직렬화
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

# 큐 명시(필수는 아니지만, 워커가 없는 큐로 빠지는 사고를 줄여줌)
celery_app.conf.task_queues = (
    Queue("ocr_cpu"),
    Queue("llm_gpu"),
    Queue("postproc"),
)

__all__ = ["celery_app"]