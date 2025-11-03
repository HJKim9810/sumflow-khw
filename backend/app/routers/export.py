from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from ..services.db_service import SessionLocal, Document
from ..core.config import OUTPUT_ROOT
from ..services.zip_service import build_category_zip_by_documents

router = APIRouter(prefix="/export", tags=["Export"])

@router.get("/batch/{batch_id}")
def export_batch(batch_id: str):
    with SessionLocal() as ss:
        rows = (ss.query(Document)
                  .filter(Document.PROC_STATUS.in_(["DONE"]))  # 필요시 조건 조정
                  .all())
        docs = []
        for r in rows:
            base_dir = (OUTPUT_ROOT / r.RESULT_FOLDER_ID).as_posix()
            docs.append({
                "CATEGORY_NAME": r.CATEGORY_NAME,
                "RESULT_FOLDER_ID": r.RESULT_FOLDER_ID,
                "ORIGINAL_FILENAME": r.ORIGINAL_FILENAME,
                "BASE_DIR": base_dir,
            })

    z = build_category_zip_by_documents(batch_id, docs)
    if not z.exists():
        raise HTTPException(404, "ZIP 생성 실패")
    return FileResponse(z, media_type="application/zip", filename=z.name)