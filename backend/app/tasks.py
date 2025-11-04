# === app/tasks.py (FULL, lazy-import only; no new files; original behavior preserved) ===
from __future__ import annotations

from pathlib import Path
from celery import Celery

celery_app = Celery("app")
try:
    celery_app.config_from_object("app.workers.celery_settings")
except Exception:
    # 설정 모듈 없을 수 있음 — 서버 기동 막지 않음
    pass


@celery_app.task(name="tasks.pipeline", bind=True)
def pipeline(  # type: ignore[override]
    self,
    *,
    file_path: str,
    filename: str,
    batch_id: str,
    sha: str,
    owner_user_id: int,
):
    """
    1) OCR & merge
    2) LLM summarize (+ category)
    3) DB upsert
    """
    # ---- owner guard ----
    if not owner_user_id or int(owner_user_id) <= 0:
        raise ValueError("owner_user_id is required and must be > 0")

    # ---- resolve input ----
    src = Path(file_path).resolve()
    size = src.stat().st_size if src.exists() else 0  # except 경로에서도 사용해야 하므로 선계산

    # ---- 1) OCR & merge (임포트 지연) ----
    # 원래 경로가 동작하던 프로젝트 기준으로 먼저 시도
    try:
        from app.services.ocr_service import run_ocr_and_merge
    except Exception:
        # 보조 경로(있으면 사용; 없으면 바로 예외 발생시켜 원인 드러냄)
        try:
            from app.services.ocr import run_ocr_and_merge  # 예비
        except Exception as e:
            raise ImportError(
                f"run_ocr_and_merge import failed: "
                f"app.services.ocr_service / app.services.ocr — {type(e).__name__}: {e}"
            )
    out_dir, merged_txt_path = run_ocr_and_merge(src)

    # ---- 2) LLM summarize (+ category) (임포트 지연) ----
    try:
        from app.services.llm import summarize_to_file, normalize_category
    except Exception:
        # 보조 경로
        try:
            from app.application.services.llm import summarize_to_file, normalize_category
        except Exception as e:
            raise ImportError(
                f"LLM import failed: app.services.llm / app.application.services.llm — {type(e).__name__}: {e}"
            )

    summary_path = out_dir / "llm" / "summary.txt"
    try:
        result_llm, raw_cat = summarize_to_file(
            merged_txt_path,
            summary_path,
            title_hint=None,
            category=True,
            timeout_s=90,
        )
        summary_txt = (result_llm.get("summary") or "").strip()
        title = (result_llm.get("title") or None)
        category_name = normalize_category(raw_cat) if raw_cat else None

        # ---- 3) DB upsert (READY) (임포트 지연) ----
        try:
            from app.services.db_service import upsert_document
        except Exception:
            # 구버전 호환: 함수명이 insert_or_update_doc 인 경우
            try:
                from app.services.db_service import insert_or_update_doc as upsert_document  # type: ignore
            except Exception as e:
                # 마지막 보조 경로
                from app.db_service import upsert_document  # type: ignore

        upsert_document(
            owner_user_id=owner_user_id,
            result_folder_id=batch_id,
            original_filename=filename,
            changed_filename=None,
            category_name=category_name,
            title=title,
            summary_text=summary_txt,           # ← llm_summary_text 아님
            rel_summary_txt="llm/summary.txt",
            rel_meta_json="meta.json",
            file_size=size,
            proc_status="READY",
            last_error=None,
            batch_id=batch_id,
        )

    except Exception as e:
        # ---- 실패 시 DB upsert(FAILED) (임포트 지연 동일) ----
        try:
            from app.services.db_service import upsert_document
        except Exception:
            try:
                from app.services.db_service import insert_or_update_doc as upsert_document  # type: ignore
            except Exception:
                from app.db_service import upsert_document  # type: ignore

        err = f"{type(e).__name__}: {e}"
        upsert_document(
            owner_user_id=owner_user_id,
            result_folder_id=batch_id,
            original_filename=filename,
            changed_filename=None,
            category_name=None,
            title=None,
            summary_text=None,
            rel_summary_txt="llm/summary.txt",
            rel_meta_json="meta.json",
            file_size=size,
            proc_status="FAILED",
            last_error=(err[:1000] if err else None),
            batch_id=batch_id,
        )
        raise

    return {
        "file_id": batch_id,
        "category": category_name if "category_name" in locals() else None,
        "summary_path": str(summary_path),
    }
