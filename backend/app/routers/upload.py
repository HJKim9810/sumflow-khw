from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import uuid, shutil
from app.core.config import BASE
from app.utils.paths import classify_ext
from app.tasks import pipeline as pipeline_task
router = APIRouter(prefix="/ocr", tags=["OCR"])

TMP_UPLOAD = BASE / "tmp"
TMP_UPLOAD.mkdir(exist_ok=True, parents=True)

@router.post("/tesseract")
async def tesseract(file: UploadFile = File(...)):
    """
    프론트엔드에서 /ocr/tesseract 로 단일 파일 POST 요청시 호출됨.
    내부적으로 기존 pipeline_task 를 그대로 사용.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    file_id = uuid.uuid4().hex
    dest = TMP_UPLOAD / f"{file_id}{Path(file.filename).suffix.lower()}"
    with dest.open("wb") as w:
        shutil.copyfileobj(file.file, w)

    o = pipeline_task.delay(
       file_path=str(dest),
       filename=file.filename,
       batch_id=file_id,   # 단일 업로드는 batch_id 대신 file_id 사용
       sha=file_id,        # sha 필드도 file_id 재활용
       owner_user_id=1
   )
    return {"ok": True, "item": {"fileId": file_id, "task": o.id, "filename": file.filename}}

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
        o = pipeline_task.delay(
           file_path=str(dest),
           filename=f.filename,
           batch_id=file_id,
           sha=file_id,
           owner_user_id=1
       )
        results.append({"fileId": file_id, "task": o.id, "filename": f.filename})
    return {"ok": True, "items": results}