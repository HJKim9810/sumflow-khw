from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import datetime

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.document_model import Document
from app.models.comment_model import DocComment

router = APIRouter(prefix="/api/v1/documents", tags=["Comments"])

class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)

def _get_doc_or_404(db: Session, document_id: int) -> Document:
    doc = db.query(Document).filter(Document.DOCUMENT_ID == document_id).first()
    if not doc:
        raise HTTPException(404, "문서를 찾을 수 없습니다.")
    return doc

def _ensure_owner(user_id: int, doc: Document):
    if int(doc.OWNER_USER_ID) != int(user_id):
        raise HTTPException(403, "내 문서에만 메모를 작성/조회/삭제할 수 있습니다.")

def _serialize_comment(row: DocComment, nickname: str | None = None) -> Dict[str, Any]:
    return {
        "id": row.COMMENT_ID,
        "documentId": row.DOCUMENT_ID,
        "userId": row.USER_ID,
        "body": row.BODY,
        "isDeleted": bool(row.IS_DELETED),
        "createdAt": row.CREATED_AT.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row.CREATED_AT else None,
        "updatedAt": row.UPDATED_AT.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if row.UPDATED_AT else None,
        # 프론트 하위호환(예전 댓글 UI가 authorNickname을 기대할 수 있어서 토큰의 닉네임을 넣어줌)
        "authorNickname": nickname or "나",
    }

@router.get("/{document_id}/comments")
def list_comments(
    document_id: int,
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(401, "인증 정보가 없습니다.")

    doc = _get_doc_or_404(db, document_id)
    _ensure_owner(user_id, doc)

    rows = (
        db.query(DocComment)
        .filter(
            DocComment.DOCUMENT_ID == document_id,
            DocComment.IS_DELETED == False,  # 소프트 삭제 제외
        )
        .order_by(DocComment.CREATED_AT.desc())
        .all()
    )

    nickname = payload.get("nickname")
    return {"items": [_serialize_comment(r, nickname) for r in rows]}

@router.post("/{document_id}/comments")
def create_comment(
    document_id: int,
    req: CommentCreate,
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(401, "인증 정보가 없습니다.")

    doc = _get_doc_or_404(db, document_id)
    _ensure_owner(user_id, doc)

    body = req.body.strip()
    if not body:
        raise HTTPException(400, "본문이 비었습니다.")

    row = DocComment(
        DOCUMENT_ID=document_id,
        USER_ID=int(user_id),
        BODY=body,
        IS_DELETED=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return _serialize_comment(row, payload.get("nickname"))

@router.delete("/{document_id}/comments/{comment_id}")
def soft_delete_comment(
    comment_id: int,
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(401, "인증 정보가 없습니다.")

    row = db.query(DocComment).filter(DocComment.COMMENT_ID == comment_id).first()
    if not row or row.IS_DELETED:
        raise HTTPException(404, "댓글을 찾을 수 없습니다.")

    # 본인 문서만: 문서 소유자만 삭제 가능 (또는 작성자 본인만 허용하려면 조건 변경)
    doc = _get_doc_or_404(db, row.DOCUMENT_ID)
    _ensure_owner(user_id, doc)

    row.IS_DELETED = True
    db.add(row)
    db.commit()
    return {"success": True}