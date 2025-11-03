from pathlib import Path
# backend/app/tasks.py
from app.core.celery_app import celery_app
from app.services.ocr import run_ocr
from app.services.llm import summarize_to_file
from app.services.db_service import upsert_document
from app.utils.category_name import normalize_category
import json, uuid

@celery_app.task(name="tasks.ocr_cpu")
def ocr_cpu_task(file_path: str, filename: str, file_id: str, owner_user_id: int):
    out = run_ocr(Path(file_path), file_id)
    size = Path(file_path).stat().st_size if Path(file_path).exists() else 0

    upsert_document(
        owner_user_id=owner_user_id,
        result_folder_id=file_id,
        original_filename=filename,
        file_size=size,
        proc_status="DONE",   
        rel_meta_json="meta.json",
    )
    return {"file_id": file_id, **out}

@celery_app.task(name="tasks.llm_gpu")
def llm_gpu_task(file_id: str, out_dir: str, owner_user_id: int, original_filename: str, file_size: int):
    merged = Path(out_dir) / "merged.txt"
    summary_path = Path(out_dir) / "llm" / "summary.txt"
    result, raw_cat = summarize_to_file(merged, summary_path)
    cat = normalize_category(raw_cat)

    upsert_document(
        owner_user_id=owner_user_id,
        result_folder_id=file_id,
        original_filename=original_filename,
        file_size=file_size,
        category_name=cat,
        summary_text=result,
        proc_status="DONE",
        rel_summary_dir="llm/",
        rel_meta_json="meta.json",
    )
    return {"file_id": file_id, "category": cat}

@celery_app.task(name="tasks.postproc")
def postproc_task(file_id: str, out_dir: str):
    insert_or_update_doc(file_id, None, out_dir, status="READY")
    return {"file_id": file_id}

@celery_app.task(
    name="tasks.pipeline",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def pipeline(
    self,
    *,
    file_path: str,
    filename: str,
    batch_id: str,
    sha: str,
    owner_user_id: int = 1
):
    """
    한 파일에 대해 OCR -> LLM -> 파일/DB 반영 -> 배치 메타 기록
    - file_path: 로컬에 저장된 원본 파일 경로
    - filename: 원본 파일명(화면/로그 용)
    - batch_id: 업로드 묶음 식별자
    - sha: 파일 해시(충돌 방지용), 상위에서 이미 계산되었다고 가정
    - owner_user_id: 문서 소유자(기본 1)
    """
    # --- 경로 구성 ---
    base = Path(OUTPUT_ROOT)
    uploads = (base / "uploads" / batch_id)
    results = (base / "results")
    file_id = sha[:12] if sha else uuid.uuid4().hex[:12]
    out_dir = uploads / file_id
    out_dir.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    src = Path(file_path)
    if not src.is_absolute():
        src = src.resolve()

    # --- 상태 표시 ---
    self.update_state(state="STARTED", meta={"stage": "INIT", "filename": filename})

    # --- 1) OCR (merge 엔진 호출은 services/ocr.run_ocr 내부에서 수행됨) ---
    self.update_state(state="PROGRESS", meta={"stage": "OCR", "filename": filename})
    ocr_out = run_ocr(src, file_id)  # 규약: {"merged_text": "...", "pages": n, ...}

    merged_txt_path = out_dir / "merged.txt"
    if not merged_txt_path.exists():
        # 3단계 구현이 merged.txt를 이미 저장하지만, 방어차원
        merged_txt_path.write_text(ocr_out.get("merged_text", ""), encoding="utf-8")

    # --- 2) LLM 요약 ---
    self.update_state(state="PROGRESS", meta={"stage": "LLM", "filename": filename})
    summary_path = out_dir / "llm" / "summary.txt"
    result_llm, raw_cat = summarize_to_file(merged_txt_path, summary_path, title_hint=None, category=True, timeout_s=90)
    summary_txt = result_llm.get("summary", "")
    title = result_llm.get("title") or None
    category_name = normalize_category(raw_cat) if raw_cat else None

    # --- 3) 메타파일(meta.json) 기록 ---
    meta = {
        "file_id": file_id,
        "batch_id": batch_id,
        "filename": filename,
        "pages": ocr_out.get("pages"),
        "title": title,
        "category": category_name,
        "paths": {
            "summary_txt": "llm/summary.txt",
            "meta_json": "meta.json"
        }
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 4) DB upsert ---
    size = src.stat().st_size if src.exists() else 0
    # maintable2.sql 기준 컬럼 매핑
    upsert_document(
        owner_user_id=owner_user_id,
        result_folder_id=file_id,
        batch_id=batch_id,
        original_filename=filename,
        changed_filename=None,
        category_name=category_name,
        title=title,
        llm_summary_text=summary_txt,
        rel_summary_txt="llm/summary.txt",
        rel_meta_json="meta.json",
        file_size=size,
        proc_status="READY",     # READY로 완료 표기(스키마 ENUM)
        last_error=None,
    )

    # --- 5) 배치 메타 누적(results/<batch>.json) ---
    batch_meta_path = results / f"{batch_id}.json"
    batch_meta = {"batch_id": batch_id, "tasks": []}
    if batch_meta_path.exists():
        try:
            batch_meta = json.loads(batch_meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    batch_meta.setdefault("tasks", []).append({
        "task_id": self.request.id,
        "file_id": file_id,
        "filename": filename
    })
    batch_meta_path.write_text(json.dumps(batch_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- 완료 ---
    self.update_state(state="SUCCESS", meta={"stage": "DONE", "filename": filename})
    return {
        "file_id": file_id,
        "category": category_name,
        "summary_path": str(summary_path)
    }
