import uuid
from pathlib import Path
from .core.celery_app import celery_app
from .services.ocr import run_ocr
from .services.llm import summarize_to_file
from .services.db_service import insert_or_update_doc, upsert_document
from .utils.category_name import normalize_category

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