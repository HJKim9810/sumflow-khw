# app/routers/upload.py — 동기 파이프라인(임시), 에러는 항상 JSON으로 반환

from __future__ import annotations

import base64
import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import JSONResponse

# 내부 설정/서비스
from app.core.config import BASE
from app.services.ocr import run_ocr  # OCR → (out_dir, merged.txt, meta) 생성
from app.services.llm import summarize_to_file  # merged.txt → llm/summary.txt
from app.services.db_service import upsert_document  # DB 반영
from app.utils.category_name import normalize_category

logger = logging.getLogger("app")

router = APIRouter(prefix="/ocr", tags=["OCR"])

# 저장 루트(기존 패턴 유지): app/ocr_store/uploads/<file_id>/<file_id>/<filename>
STORE_ROOT = (BASE / "ocr_store" / "uploads")
STORE_ROOT.mkdir(parents=True, exist_ok=True)


# ---------------- helpers ----------------
def _safe_filename(name: Optional[str]) -> str:
    if not name:
        return "upload.bin"
    bad = '<>:"/\\|?*'
    for ch in bad:
        name = name.replace(ch, "_")
    return name.strip() or "upload.bin"


def _save_upload(dest_dir: Path, up: UploadFile) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _safe_filename(up.filename)
    try:
        up.file.seek(0)
    except Exception:
        pass
    with dest.open("wb") as f:
        shutil.copyfileobj(up.file, f)
    return dest


def _extract_user_id_from_auth_header(request: Request) -> Optional[int]:
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    try:
        token = auth.split(" ", 1)[1].strip()
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8", "ignore"))
        for key in ("user_id", "id", "uid", "sub"):
            v = payload.get(key)
            if isinstance(v, (int, str)) and str(v).isdigit():
                return int(v)
    except Exception:
        return None
    return None


def _resolve_owner_id(request: Request, owner_user_id, user_id, userId) -> int:
    """
    owner 결정 순서:
      1) form: owner_user_id / user_id / userId
      2) header: X-User-Id
      3) Authorization: Bearer <JWT> (payload.user_id|id|uid|sub)
      4) 기본값 1 (프론트 미전달 시 파이프라인 막지 않기 위함)
    """
    oid = owner_user_id or user_id or userId
    if oid is None:
        h = request.headers.get("X-User-Id") or request.headers.get("x-user-id")
        if h and str(h).isdigit():
            oid = int(h)
    if oid is None:
        oid = _extract_user_id_from_auth_header(request)
    if oid is None:
        oid = 1
    return int(oid)


def _summary_preview(s: str | None, limit: int = 1200) -> str | None:
    if not s:
        return None
    return (s[:limit] + "...") if len(s) > limit else s


# ---------------- routes ----------------
@router.post("/tesseract")
async def tesseract(
    request: Request,
    file: UploadFile = File(...),
    owner_user_id: int | None = Form(None),
    user_id: int | None = Form(None),
    userId: int | None = Form(None),
):
    """
    단일 파일 업로드 → (동기) OCR → (동기) LLM → DB upsert → 200 OK
    Celery는 일단 배제(지금 당장 500 차단 및 결과 확인이 목적). 이후 정상화되면 다시 비동기로 전환 가능.
    응답은 프론트가 쓰던 포맷을 유지: { ok, items: [{ fileId, filename, ... }] }
    """
    try:
        oid = _resolve_owner_id(request, owner_user_id, user_id, userId)

        # 0) 저장 경로 및 원본 저장
        file_id = uuid.uuid4().hex[:12]
        out_dir = STORE_ROOT / file_id / file_id
        src_path = _save_upload(out_dir, file)

        # 1) OCR
        ocr_out = run_ocr(src_path, file_id)  # dict: out_dir(str), pages(int), meta(dict)...
        out_dir2 = Path(ocr_out.get("out_dir") or out_dir)
        pages = int(ocr_out.get("pages") or 0)
        meta = ocr_out.get("meta") or {}

        merged_path = out_dir2 / "merged.txt"
        if not merged_path.exists():
            raise FileNotFoundError(f"merged.txt not found: {merged_path}")

        # 2) LLM 요약
        summary_out = out_dir2 / "llm" / "summary.txt"
        result_llm, raw_cat = summarize_to_file(
            merged_path, summary_out,
            title_hint=None,
            category=True,
            timeout_s=480,
        )
        summary_txt = (result_llm.get("summary") or "").strip()
        title = (result_llm.get("title") or None)
        category_name = normalize_category(raw_cat) if raw_cat else None

        # 3) DB upsert
        upsert_document(
            owner_user_id=oid,
            result_folder_id=file_id,
            original_filename=_safe_filename(file.filename),
            changed_filename=None,
            file_size=src_path.stat().st_size if src_path.exists() else 0,
            category_name=category_name,
            title=title,
            summary_text=summary_txt or None,
            summary_relpath="llm/summary.txt",
            meta_relpath="meta.json",
            proc_status="READY",
            last_error=None,
            batch_id=file_id,
        )

        # 4) 응답
        return {
            "ok": True,
            "items": [{
                "fileId": file_id,
                "filename": _safe_filename(file.filename),
                "ownerUserId": oid,
                "pages": pages,
                "category": category_name,
                "status": "READY",
                "summaryPreview": _summary_preview(summary_txt),
            }],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[/ocr/tesseract] unhandled error")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "internal_error", "detail": str(e)},
        )


@router.post("/upload")
async def upload_multi(
    request: Request,
    files: List[UploadFile] = File(...),
    owner_user_id: int | None = Form(None),
    user_id: int | None = Form(None),
    userId: int | None = Form(None),
):
    """
    멀티 파일도 동기 처리(파일마다 순차).
    """
    try:
        oid = _resolve_owner_id(request, owner_user_id, user_id, userId)
        outputs: List[dict] = []

        for up in files:
            try:
                file_id = uuid.uuid4().hex[:12]
                out_dir = STORE_ROOT / file_id / file_id
                src_path = _save_upload(out_dir, up)

                ocr_out = run_ocr(src_path, file_id)
                out_dir2 = Path(ocr_out.get("out_dir") or out_dir)
                pages = int(ocr_out.get("pages") or 0)

                merged_path = out_dir2 / "merged.txt"
                if not merged_path.exists():
                    raise FileNotFoundError(f"merged.txt not found: {merged_path}")

                summary_out = out_dir2 / "llm" / "summary.txt"
                result_llm, raw_cat = summarize_to_file(
                    merged_path, summary_out,
                    title_hint=None,
                    category=True,
                    timeout_s=90,
                )
                summary_txt = (result_llm.get("summary") or "").strip()
                title = (result_llm.get("title") or None)
                category_name = normalize_category(raw_cat) if raw_cat else None

                upsert_document(
                    owner_user_id=oid,
                    result_folder_id=file_id,
                    original_filename=_safe_filename(up.filename),
                    changed_filename=None,
                    file_size=src_path.stat().st_size if src_path.exists() else 0,
                    category_name=category_name,
                    title=title,
                    summary_text=summary_txt or None,
                    summary_relpath="llm/summary.txt",
                    meta_relpath="meta.json",
                    proc_status="READY",
                    last_error=None,
                    batch_id=file_id,
                )

                outputs.append({
                    "fileId": file_id,
                    "filename": _safe_filename(up.filename),
                    "ownerUserId": oid,
                    "pages": pages,
                    "category": category_name,
                    "status": "READY",
                    "summaryPreview": _summary_preview(summary_txt),
                })
            except Exception as e:
                logger.exception("[/ocr/upload] per-file failed")
                outputs.append({
                    "fileId": file_id,
                    "filename": _safe_filename(up.filename),
                    "error": "internal_error",
                    "detail": str(e),
                })

        return {"ok": True, "items": outputs, "ownerUserId": oid}

    except Exception as e:
        logger.exception("[/ocr/upload] unhandled error")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "internal_error", "detail": str(e)},
        )