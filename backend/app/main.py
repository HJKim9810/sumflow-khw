import os, io, uuid, zipfile, jwt
import logging, traceback, json, time, re, unicodedata
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from sqlalchemy import text

from dotenv import load_dotenv
load_dotenv()

import anyio

# --- 내부 서비스/유틸 ---
from app.services.ocr import ocr_funnel_extract, batch_ocr_zip
from app.services.llm import summarize_and_categorize
from app.services.db_service import insert_or_update_doc
from app.utils.version import get_version
from app.utils.telemetry import Telemetry, PerfRecorder
from app.core.db import SessionLocal
from app.core.security import decode_access_token
from app.models.visitlog_model import VisitLog
from app.models.user_model import AppUser

# =========================
# 기본 설정/로그
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("app")

APP_NAME = "ocr-llm-suite"

# 파일 저장 루트 (outputs/<RESULT_FOLDER_ID>/…)
OUTPUT_ROOT = Path(os.getenv("OUTPUT_ROOT", "outputs")).resolve()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 임시 청크 세션 저장 루트
SESS_ROOT = Path("tmp/sessions")
SESS_ROOT.mkdir(parents=True, exist_ok=True)

# Ollama 정보 로그
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_HOST  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
logger.info(f"🧠 Using Ollama model: {OLLAMA_MODEL}")
logger.info(f"🌐 Ollama host: {OLLAMA_HOST}")

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# =========================
# 방문 로그 미들웨어 (하루 1회/유저)
# =========================
@app.middleware("http")
async def _visit_logger(request: Request, call_next):
    path = request.url.path
    if path.startswith(("/docs", "/redoc", "/openapi")):
        return await call_next(request)

    if request.method in ("GET", "HEAD"):
        db = SessionLocal()
        try:
            user_id = None
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth.split(" ", 1)[1]
                secret = os.getenv("JWT_SECRET", "mysecretkey")
                try:
                    payload = jwt.decode(token, secret, algorithms=["HS256"])
                    user_id = payload.get("user_id")
                    if not user_id and payload.get("sub"):
                        login_id = payload["sub"]
                        u = db.query(AppUser).filter(AppUser.LOGIN_ID == login_id).first()
                        if u:
                            user_id = u.USER_ID
                except Exception:
                    user_id = None

            if user_id:
                db.execute(
                    text("""
                        INSERT INTO VISIT_LOG (USER_ID)
                        SELECT :uid
                        WHERE NOT EXISTS (
                            SELECT 1 FROM VISIT_LOG
                             WHERE USER_ID = :uid
                               AND DATE(VISITED_AT) = CURRENT_DATE
                        )
                    """),
                    {"uid": user_id},
                )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    return await call_next(request)

# =========================
# 요청 모델
# =========================
class CompareRequest(BaseModel):
    left_text: str
    right_text: str

class CompareByIdRequest(BaseModel):
    left_id: str
    right_id: str
    mode: str = "text"

# =========================
# 헬스/버전
# =========================
@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {"version": get_version(), "name": APP_NAME}

# =========================
# 도우미: 카테고리 파싱/정규화
# =========================
_CAT_CLEAN = re.compile(r"[()\[\]{}#*「」『』<>]")
def _normalize_category(raw: Optional[str]) -> str:
    if not raw:
        return "미분류/기타"
    s = _CAT_CLEAN.sub("", raw.strip())
    parts = re.split(r"[>\-\|;,·•∙▶▷➡️→]+|\s*/\s*", s)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if len(parts) == 1:
        return f"{parts[0]}/기타"
    return "미분류/기타"

def _extract_category_from_summary(summary: str) -> str:
    """
    요약문에서 '카테고리:' 줄을 찾아 카테고리 문자열 추출
    """
    m = re.search(r"^\s*카테고리\s*:\s*(.+)$", summary or "", flags=re.MULTILINE)
    return _normalize_category(m.group(1) if m else None)

# =========================
# 도우미: 결과 저장 (파일시스템)
# =========================
def _write_outputs(folder_id: str, original_name: str, blob: bytes, text: str, summary: str, meta: dict):
    """
    outputs/<folder_id>/
      ├─ original.ext
      ├─ merged.txt
      ├─ llm/summary.txt
      ├─ meta.json
      └─ log.txt
    """
    out_dir = OUTPUT_ROOT / folder_id
    (out_dir / "llm").mkdir(parents=True, exist_ok=True)

    # 원본 저장 (확장자 유지)
    ext = Path(original_name).suffix or ".bin"
    (out_dir / f"original{ext}").write_bytes(blob)

    # 텍스트/요약/메타/로그
    (out_dir / "merged.txt").write_text(text or "", encoding="utf-8")
    (out_dir / "llm" / "summary.txt").write_text(summary or "", encoding="utf-8")
    (out_dir / "meta.json").write_text(json.dumps(meta or {}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "log.txt").write_text("OCR_DONE\n", encoding="utf-8")

    return out_dir

# =========================
# LLM 워밍업
# =========================
@app.on_event("startup")
async def _warm_llm():
    try:
        logger.info("🔥 Warming up LLM model...")
        await anyio.to_thread.run_sync(summarize_and_categorize, "warmup")
        logger.info("🔥 LLM warmup complete.")
    except Exception as e:
        logger.warning(f"🔥 LLM warmup failed: {e}")

# =========================
# 업로드: OCR → LLM → 저장 → DB upsert
# =========================
@app.post("/api/v1/ocr/upload")
async def upload(
    files: List[UploadFile] = File(...),
    batch_id: Optional[str] = Form(None),
    token_data: dict = Depends(decode_access_token)  # 로그인한 사용자라면 user_id 획득
):
    perf = PerfRecorder(enabled=os.getenv("PERF_ENABLED", "false").lower() == "true")
    telemetry = Telemetry()
    results = []

    owner_user_id = token_data.get("user_id") if token_data else None
    if not owner_user_id:
        # 비로그인 업로드도 허용하려면 0 또는 시스템 계정 등으로 처리
        owner_user_id = int(os.getenv("DEFAULT_OWNER_USER_ID", "1"))

    if not batch_id:
        batch_id = time.strftime("batch_%Y%m%d")

    for f in files:
        blob = await f.read()
        filename = f.filename or f"file-{uuid.uuid4().hex}.bin"
        size = len(blob)
        logger.info(f"📥 RECEIVED FILE: {filename}, size={size} bytes")

        # 1) OCR (동기)
        try:
            with perf.step(f"ocr:{filename}"):
                text, pages, meta, per_page_texts = ocr_funnel_extract(blob, filename=filename, mode="quality")
        except Exception as e:
            logger.exception(f"❌ OCR failed: {filename}")
            raise HTTPException(status_code=500, detail=f"OCR failed for {filename}: {e}")

        # 2) LLM 요약 (워커 스레드)
        try:
            with perf.step(f"llm:{filename}"):
                summary = await anyio.to_thread.run_sync(summarize_and_categorize, text)
        except Exception as e:
            logger.exception(f"❌ LLM failed: {filename}")
            # 실패 시에도 최소 메타는 기록
            summary = ""
            # 계속 저장은 진행하되 상태는 FAILED로
            proc_status = "FAILED"
            last_error  = f"LLM error: {e}"
        else:
            proc_status = "READY"
            last_error  = None

        # 3) 결과 저장 (파일시스템)
        folder_id = uuid.uuid4().hex
        out_dir = _write_outputs(folder_id, filename, blob, text, summary, meta)

        # 4) 카테고리 추출
        category_name = _extract_category_from_summary(summary)

        # 5) DB upsert
        try:
            insert_or_update_doc(
                owner_user_id=owner_user_id,
                result_folder_id=folder_id,
                original_filename=filename,
                changed_filename=None,
                file_size=size,
                category_name=category_name,
                title=meta.get("title") if isinstance(meta, dict) else None,
                summary_text=summary or None,
                summary_relpath="llm/summary.txt",
                meta_relpath="meta.json",
                proc_status=proc_status,
                last_error=last_error,
                batch_id=batch_id,
            )
        except Exception as e:
            logger.exception(f"❌ DB upsert failed: {filename}")
            # DB 실패는 응답 자체를 실패로 돌리고 싶다면 아래 줄을 활성화
            # raise HTTPException(status_code=500, detail=f"DB upsert failed: {e}")

        results.append({
            "result_folder_id": folder_id,
            "filename": filename,
            "pages": pages,
            "category": category_name,
            "summary_preview": (summary[:1200] + "...") if summary and len(summary) > 1200 else summary,
            "status": proc_status,
        })

    telemetry.merge(perf.to_telemetry())
    return {"ok": True, "batch_id": batch_id, "items": results, "telemetry": telemetry.data}

# =========================
# 텍스트 직접 비교
# =========================
@app.post("/api/v1/ocr/compare")
def compare(payload: CompareRequest):
    a = payload.left_text or ""
    b = payload.right_text or ""
    set_a = set(a.split())
    set_b = set(b.split())
    only_a = sorted(list(set_a - set_b))[:100]
    only_b = sorted(list(set_b - set_a))[:100]
    overlap = sorted(list(set_a & set_b))[:100]
    return {
        "left_unique_terms_preview": only_a,
        "right_unique_terms_preview": only_b,
        "overlap_terms_preview": overlap,
        "left_len": len(a),
        "right_len": len(b),
    }

# =========================
# (레거시) doc_id 기준 비교용 임시 저장소
#  - 새 구조에선 outputs/<folder_id>/merged.txt를 직접 읽어 쓰는 게 맞지만
#  - 기존 기능 호환을 위해 유지 (필요 없으면 제거 가능)
# =========================
STORE_DIR = Path("tmp/ocr_store")
STORE_DIR.mkdir(parents=True, exist_ok=True)

def _store_doc(doc_id: str, payload: dict):
    (STORE_DIR / f"{doc_id}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

def _load_doc(doc_id: str) -> dict:
    p = STORE_DIR / f"{doc_id}.json"
    if not p.exists():
        raise FileNotFoundError(doc_id)
    return json.loads(p.read_text(encoding="utf-8"))

@app.post("/api/v1/ocr/compare_by_id")
def compare_by_id(payload: CompareByIdRequest):
    left = _load_doc(payload.left_id)
    right = _load_doc(payload.right_id)

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFC", s)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    a = norm(left.get("full_text", "") or "")
    b = norm(right.get("full_text", "") or "")

    ta = re.findall(r"\w+", a)
    tb = re.findall(r"\w+", b)
    sa, sb = set(ta), set(tb)

    return {
        "mode": "text",
        "left_len": len(a),
        "right_len": len(b),
        "jaccard_overlap": round(len(sa & sb) / max(1, len(sa | sb)), 4),
        "left_unique_terms_preview": sorted(list(sa - sb))[:100],
        "right_unique_terms_preview": sorted(list(sb - sa))[:100],
    }

# =========================
# ZIP 일괄 업로드 (→ 각 파일 요약 JSON을 ZIP으로 응답)
#  * 파일시스템/DB 반영까지 하고 싶다면 위 upload()와 동일 로직을 넣어 확장 가능
# =========================
@app.post("/api/v1/ocr/zip")
async def upload_zip(zip_file: UploadFile = File(...)):
    perf = PerfRecorder(enabled=os.getenv("PERF_ENABLED", "false").lower() == "true")
    telemetry = Telemetry()

    data = await zip_file.read()
    memzip = io.BytesIO()

    with zipfile.ZipFile(memzip, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name, text, pages in batch_ocr_zip(data):
            with perf.step(f"llm:{name}"):
                summary = await anyio.to_thread.run_sync(summarize_and_categorize, text)
            result = {"filename": name, "pages": pages, "summary": summary}
            zout.writestr(f"{name}.json", json.dumps(result, ensure_ascii=False, indent=2))

    telemetry.merge(perf.to_telemetry())
    memzip.seek(0)
    headers = {"X-Telemetry": json.dumps(telemetry.data)}
    return StreamingResponse(memzip, media_type="application/zip", headers=headers)

# =========================
# 청크 업로드 세션 (대용량 파일)
# =========================
@app.post("/api/v1/upload/session")
def create_session():
    sid = str(uuid.uuid4())
    (SESS_ROOT / f"{sid}.part").write_bytes(b"")
    return {"session_id": sid}

@app.patch("/api/v1/upload/session/{sid}")
async def append_chunk(sid: str, chunk: UploadFile = File(...)):
    path = SESS_ROOT / f"{sid}.part"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "session not found"})
    data = await chunk.read()
    with open(path, "ab") as f:
        f.write(data)
    return {"ok": True, "bytes": len(data)}

@app.post("/api/v1/upload/session/{sid}/finalize")
async def finalize_session(
    sid: str,
    is_zip: bool = Form(True),
    batch_id: Optional[str] = Form(None),
    token_data: dict = Depends(decode_access_token),
):
    path = SESS_ROOT / f"{sid}.part"
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "session not found"})

    blob = path.read_bytes()
    path.unlink(missing_ok=True)

    if is_zip:
        memzip = io.BytesIO()
        with zipfile.ZipFile(memzip, 'w', zipfile.ZIP_DEFLATED) as zout:
            for name, text, pages in batch_ocr_zip(blob):
                summary = await anyio.to_thread.run_sync(summarize_and_categorize, text)
                result = {"filename": name, "pages": pages, "summary": summary}
                zout.writestr(f"{name}.json", json.dumps(result, ensure_ascii=False, indent=2))
        memzip.seek(0)
        return StreamingResponse(memzip, media_type="application/zip")

    # 단일 파일 흐름(업로드와 동일)
    owner_user_id = token_data.get("user_id") if token_data else int(os.getenv("DEFAULT_OWNER_USER_ID", "1"))
    if not batch_id:
        batch_id = time.strftime("batch_%Y%m%d")

    try:
        text, pages, meta, per_page_texts = ocr_funnel_extract(blob, filename="upload.bin", mode="quality")
        summary = await anyio.to_thread.run_sync(summarize_and_categorize, text)
        proc_status, last_error = "READY", None
    except Exception as e:
        summary, proc_status, last_error = "", "FAILED", f"{e}"

    folder_id = uuid.uuid4().hex
    out_dir = _write_outputs(folder_id, "upload.bin", blob, text, summary, meta)
    category_name = _extract_category_from_summary(summary)

    insert_or_update_doc(
        owner_user_id=owner_user_id,
        result_folder_id=folder_id,
        original_filename="upload.bin",
        file_size=len(blob),
        category_name=category_name,
        title=meta.get("title") if isinstance(meta, dict) else None,
        summary_text=summary or None,
        summary_relpath="llm/summary.txt",
        meta_relpath="meta.json",
        proc_status=proc_status,
        last_error=last_error,
        batch_id=batch_id,
    )
    return {"result_folder_id": folder_id, "pages": pages, "summary": summary, "status": proc_status}

# =========================
# 인증 보조
# =========================
@app.post("/api/v1/logout")
def logout_alias(token_data: dict = Depends(decode_access_token)):
    return {"success": True}

# =========================
# 기존 라우터들
# =========================
from app.services.captcha import router as captcha_router
from app.services.signup import router as signup_router
from app.services.login import router as login_router
from app.routers.admin_router import router as admin_router
from app.routers.user_check_router import router as user_check_router
from app.routers.email_verify_router import router as email_verify_router
from app.routers.mypage_router import router as mypage_router
from app.routers import comments
from app.routers.upload import router as upload_router
from app.routers.status import router as status_router
from app.routers.export import router as export_router
from app.routers.account_recovery_router import router as account_recovery_router

app.include_router(captcha_router)
app.include_router(signup_router)
app.include_router(login_router)
app.include_router(admin_router)
app.include_router(user_check_router)
app.include_router(email_verify_router)
app.include_router(mypage_router)
app.include_router(comments.router)
app.include_router(account_recovery_router)
app.include_router(upload_router)
app.include_router(status_router)
app.include_router(export_router)