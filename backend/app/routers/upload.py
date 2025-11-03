from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import uuid, shutil
from ..core.config import BASE
from ..utils.paths import classify_ext
from ..tasks import ocr_cpu_task, llm_gpu_task, postproc_task

router = APIRouter(prefix="/ocr", tags=["OCR"])

TMP_UPLOAD = BASE / "tmp"
TMP_UPLOAD.mkdir(exist_ok=True, parents=True)

@router.post("/upload")
async def upload(files: list[UploadFile] = File(...)):
    results = []
    for f in files:
        if not f.filename:
            continue
        file_id = uuid.uuid4().hex
        dest = TMP_UPLOAD / f"{file_id}{Path(f.filename).suffix.lower()}"
        with dest.open("wb") as w:
            shutil.copyfileobj(f.file, w)

        # 파이프라인: OCR → LLM → postproc (체이닝은 클라이언트에서 /task/status 조회로)
        o = ocr_cpu_task.delay(str(dest), f.filename, file_id)
        results.append({"fileId": file_id, "task": o.id, "filename": f.filename})
    return {"ok": True, "items": results}