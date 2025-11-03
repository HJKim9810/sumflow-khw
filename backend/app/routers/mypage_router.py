# app/routers/mypage_router.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.user_model import AppUser
from app.models.document_model import Document
from sqlalchemy import or_, and_

router = APIRouter(
    prefix="/api/v1/user/mypage",
    tags=["MyPage"],
)

def _to_profile_json(u: AppUser) -> Dict[str, Any]:
    """프론트 MyPage.jsx가 바로 먹기 좋은 키로 매핑(원본 스타일 최대 보존)"""
    return {
        "userId": u.USER_ID,
        "loginId": u.LOGIN_ID,
        "name": u.NAME,
        "email": u.EMAIL,
        "phone": u.PHONE_NUMBER,
        "nickname": u.NICKNAME,
        "isAdmin": bool(u.IS_ADMIN),
        "lastLoginAt": u.LAST_LOGIN_AT.isoformat() if u.LAST_LOGIN_AT else None,
        "createdAt": u.CREATED_AT.isoformat() if u.CREATED_AT else None,
    }

def _to_doc_item_json(d: Document) -> Dict[str, Any]:
    """
    MyPage.jsx가 이미 쓰고 있는 아이템 모양에 최대한 맞춤.
    - id, filename, size, createdAt, serverFileId, title, catPath, procStatus
    """
    return {
        "id": d.DOCUMENT_ID,
        "filename": d.ORIGINAL_FILENAME or d.CHANGED_FILENAME or "",
        "size": int(d.FILE_SIZE_BYTES or 0),
        "createdAt": d.CREATED_AT.isoformat() if d.CREATED_AT else None,
        # serverFileId는 현재 설계상 명시적 키가 없어 DOCUMENT_ID로 대체 (프론트가 다운로드 링크 만들 때 사용)
        "serverFileId": str(d.DOCUMENT_ID),
        "title": d.TITLE or "",
        "catPath": d.CATEGORY_NAME or "",   # "주/부" 형태가 아니어도 우선 문자열로 연결
        "procStatus": d.PROC_STATUS or "UPLOADED",
    }

@router.get("", summary="로그인한 사용자의 프로필 정보")
def get_my_profile(
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="인증 정보가 없습니다.")
    u = db.query(AppUser).filter(AppUser.USER_ID == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return {
        "success": True,
        "user": {
            "userId": u.USER_ID,
            "loginId": u.LOGIN_ID,
            "name": u.NAME,
            "nickname": u.NICKNAME,
            "email": u.EMAIL,
            "phone": u.PHONE_NUMBER,       # ✅ 프론트가 기대하는 key
            "IS_ADMIN": bool(u.IS_ADMIN),
            "createdAt": u.CREATED_AT.isoformat() if u.CREATED_AT else None,
        },
    }


@router.get("/documents", summary="내 문서 목록(검색/페이징)")
def get_my_documents(
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
    q: Optional[str] = Query("", description="파일명/제목 검색"),
    category: Optional[List[str]] = Query(None, description="카테고리(복수)"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="인증 정보가 없습니다.")

    query = db.query(Document).filter(Document.OWNER_USER_ID == user_id)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Document.ORIGINAL_FILENAME.ilike(like),
                Document.CHANGED_FILENAME.ilike(like),
                Document.TITLE.ilike(like),
                Document.CATEGORY_NAME.ilike(like),
            )
        )

    if category:
        # 프론트는 "주/부" 형태도 올 수 있으나, 현재 스키마엔 CATEGORY_NAME 단일 칼럼이므로 부분일치로 우선 처리
        conds = [Document.CATEGORY_NAME.ilike(f"%{c}%") for c in category if c]
        if conds:
            query = query.filter(or_(*conds))

    total = query.count()
    items = (
        query.order_by(Document.CREATED_AT.desc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )

    return {
        "success": True,
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "items": [_to_doc_item_json(d) for d in items],
    }
    
@router.patch("", summary="내 프로필 수정")
def update_my_profile(
    data: dict,
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    u = db.query(AppUser).filter(AppUser.USER_ID == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # ✅ 빈 문자열("")은 무시하고, 실제 값만 반영
    if "nickname" in data and str(data["nickname"]).strip():
        u.NICKNAME = data["nickname"].strip()
    if "phone" in data and str(data["phone"]).strip():
        u.PHONE_NUMBER = data["phone"].strip()
    if "email" in data and str(data["email"]).strip():
        u.EMAIL = data["email"].strip()

    db.commit()
    db.refresh(u)
    return {
        "success": True,
        "user": {
            "nickname": u.NICKNAME,
            "phone": u.PHONE_NUMBER,
            "email": u.EMAIL,
        },
    }

# ----------------------------------------
# 마이페이지 카테고리 로드용
# ----------------------------------------
@router.get("/categories", summary="내 문서에서 사용된 카테고리 집계")
def get_my_categories(
    payload: dict = Depends(decode_access_token),
    db: Session = Depends(get_db),
):
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="인증 정보가 없습니다.")

    # 내 문서들 중 CATEGORY_NAME만 모음
    rows = (
        db.query(Document.CATEGORY_NAME)
        .filter(Document.OWNER_USER_ID == user_id)
        .filter(Document.CATEGORY_NAME.isnot(None))
        .all()
    )
    # rows 형태: [("법률/행정",), ("법률/행정",), ("교육/제도",), ("재무",), ...]
    raw_names = { (r[0] or "").strip() for r in rows if r[0] }

    # 파싱
    # 예: "법률/행정" -> main="법률", sub="행정"
    # 예: "재무"      -> main="재무", sub=None
    pairs = []
    mains_set = set()
    for cat in raw_names:
        parts = [p.strip() for p in cat.split("/") if p.strip()]
        if len(parts) >= 2:
            main, sub = parts[0], parts[1]
        elif len(parts) == 1:
            main, sub = parts[0], None
        else:
            continue

        mains_set.add(main)
        pairs.append({
            "main": main,
            "sub": sub,
            "catPath": sub and f"{main}/{sub}" or main,
        })

    # mains = ["법률","교육","재무", ...] 같은 상위 카테고리 목록
    mains = sorted(list(mains_set))

    # 중복 catPath 제거 
    dedup = {}
    for p in pairs:
        key = p["catPath"]
        if key not in dedup:
            dedup[key] = p
    pairs_unique = list(dedup.values())

    return {
        "success": True,
        "categories": pairs_unique,  # [{main:"법률", sub:"행정", catPath:"법률/행정"}, ...]
        "mains": mains,              # ["법률","교육","재무", ...]
    }