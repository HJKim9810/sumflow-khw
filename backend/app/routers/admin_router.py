from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from core.deps import get_db
from models.user_model import AppUser
from models.document_model import Document
from models.visitlog_model import VisitLog  
from sqlalchemy import func
from schemas.admin_schema import AdminFileListResponse, AdminFileItem
from services.admin_service import (list_files_service, soft_delete_document_service,)


router = APIRouter(prefix="/admin", tags=["Admin"])

# ----------------------------------------
# /admin/stats/summary
# ----------------------------------------
@router.get("/stats/summary")
def get_admin_stats_summary(
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    day_7_ago = now - timedelta(days=7)
    day_30_ago = now - timedelta(days=30)

    # 전체 회원 수 (ACTIVE + DELETED 다 포함할거면 그냥 count 전체)
    total_all = db.query(func.count(AppUser.USER_ID)).scalar() or 0

    # 현재 회원 수 (ACTIVE)
    active_count = (
        db.query(func.count(AppUser.USER_ID))
        .filter(AppUser.STATUS == "ACTIVE")
        .scalar()
        or 0
    )

    # 탈퇴 회원 수 (DELETED)
    deleted_count = (
        db.query(func.count(AppUser.USER_ID))
        .filter(AppUser.STATUS == "DELETED")
        .scalar()
        or 0
    )

    # 최근 30일 신규 가입 수
    new_users_30d = (
        db.query(func.count(AppUser.USER_ID))
        .filter(
            AppUser.CREATED_AT >= day_30_ago,
            AppUser.STATUS == "ACTIVE",
        )
        .scalar()
        or 0
    )

    # 4) 최근 7일 업로드 수 (날짜별)
    #    DOCUMENT.CREATED_AT 기준으로 일자별 count
    uploads_rows = (
        db.query(
            func.date_format(Document.CREATED_AT, "%m/%d").label("day"),
            func.count(Document.DOCUMENT_ID).label("cnt")
        )
        .filter(Document.CREATED_AT >= day_7_ago)
        .group_by(func.date_format(Document.CREATED_AT, "%m/%d"))
        .order_by(func.date_format(Document.CREATED_AT, "%m/%d"))
        .all()
    )
    daily_uploads_7d = [
        {"day": row.day, "uploads": int(row.cnt)} for row in uploads_rows
    ]

    # 5) 최근 7일 방문 수 (VISIT_LOG.VISITED_AT 기준)
    visits_rows = (
        db.query(
            func.date_format(VisitLog.VISITED_AT, "%m/%d").label("day"),
            func.count(VisitLog.VISIT_ID).label("cnt")
        )
        .filter(VisitLog.VISITED_AT >= day_7_ago)
        .group_by(func.date_format(VisitLog.VISITED_AT, "%m/%d"))
        .order_by(func.date_format(VisitLog.VISITED_AT, "%m/%d"))
        .all()
    )
    daily_visits_7d = [
        {"day": row.day, "visits": int(row.cnt)} for row in visits_rows
    ]

    return {
        "totalUsers": int(total_all),
        "activeUsers": int(active_count),
        "deletedUsers": int(deleted_count),
        "newUsers30d": int(new_users_30d),
        "dailyUploads7d": daily_uploads_7d,
        "dailyVisits7d": daily_visits_7d,
    }

# ----------------------------------------
# 관리자 회원관리 회원 목록 조회
# ----------------------------------------
@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    nickname: str = Query("", alias="nickname"),
    name: str = Query("", alias="name"),
    email: str = Query("", alias="email"),
    status: str = Query("", alias="status"),  
):
    query = db.query(AppUser)

    # 검색 조건
    if nickname:
        query = query.filter(AppUser.NICKNAME.ilike(f"%{nickname}%"))
    if name:
        query = query.filter(AppUser.NAME.ilike(f"%{name}%"))
    if email:
        query = query.filter(AppUser.EMAIL.ilike(f"%{email}%"))

    # 상태 필터
    if status == "ACTIVE":
        query = query.filter(AppUser.STATUS == "ACTIVE")
    elif status in ("WITHDRAWN", "DELETED"):
        query = query.filter(AppUser.STATUS.in_(["WITHDRAWN", "DELETED"]))

    # 정렬 (최신 가입순)
    query = query.order_by(AppUser.CREATED_AT.desc())

    total_count = query.count()

    offset = (page - 1) * pageSize
    rows = query.offset(offset).limit(pageSize).all()

    items = []
    for u in rows:
        if u.STATUS == "ACTIVE":
            status_label = "가입"
        elif u.STATUS in ("WITHDRAWN", "DELETED"):
            status_label = "탈퇴"
        else:
            status_label = u.STATUS

        items.append({
            "id": u.USER_ID,
            "name": u.NAME,
            "nickname": u.NICKNAME,
            "email": u.EMAIL,
            "status": status_label,
            "created_at": (
                u.CREATED_AT.isoformat() if u.CREATED_AT else None
            ),
        })

    return {
        "total": total_count,
        "items": items,
    }

@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
):
    u = (
        db.query(AppUser)
        .filter(AppUser.USER_ID == user_id)
        .first()
    )
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    if u.STATUS == "ACTIVE":
        status_label = "가입"
    elif u.STATUS == "DELETED":
        status_label = "탈퇴"
    else:
        status_label = u.STATUS

    return {
        "id": u.USER_ID,
        "name": u.NAME,
        "nickname": u.NICKNAME,
        "email": u.EMAIL,
        "status": status_label,
        "created_at": u.CREATED_AT.isoformat() if u.CREATED_AT else None,
        "deleted_at": u.DELETED_AT.isoformat() if u.DELETED_AT else None,
        "last_login_at": getattr(u, "LAST_LOGIN_AT", None),
    }

@router.post("/users/{user_id}/toggle-status", status_code=http_status.HTTP_200_OK)
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
):
    u = (
        db.query(AppUser)
        .filter(AppUser.USER_ID == user_id)
        .first()
    )
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    # ACTIVE → 탈퇴 처리
    if u.STATUS == "ACTIVE":
        u.STATUS = "DELETED"  
        u.DELETED_AT = datetime.utcnow()  
        new_status_label = "탈퇴"

    # 탈퇴 상태 → 복구
    else:
        u.STATUS = "ACTIVE"
        u.DELETED_AT = None      
        new_status_label = "가입"

    db.add(u)
    db.commit()

    return {"success": True, "newStatus": new_status_label}

# ----------------------------------------
# 관리자 파일관리 목록 조회
# ----------------------------------------
@router.get("/files", response_model=AdminFileListResponse)
def get_admin_files(
    nickname: str = Query("", description="닉네임 검색"),
    filename: str = Query("", description="파일명 검색"),
    ocrStatus: str = Query("", description="DONE | FAILED | DELETED"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    # _: dict = Depends(get_current_admin),
):
    data = list_files_service(
        db=db,
        nickname=nickname,
        filename=filename,
        ocr_status=ocrStatus,
        page=page,
        page_size=pageSize,
    )
    return data


@router.patch("/files/{document_id}/delete", response_model=AdminFileItem)
def soft_delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    # _: dict = Depends(get_current_admin),
):
    doc, status = soft_delete_document_service(db, document_id)
    if status == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    # 응답을 프론트 스키마에 맞춰 변환
    ext = ""
    fn = doc.ORIGINAL_FILENAME or ""
    if "." in fn:
        ext = fn.rsplit(".", 1)[-1].lower()

    return AdminFileItem(
        id=doc.DOCUMENT_ID,
        nickname=getattr(doc, "owner", None).NICKNAME if hasattr(doc, "owner") and doc.owner else "-",  # 관계 설정시 사용
        filename=fn or "-",
        uploadedAt=doc.CREATED_AT.isoformat() if doc.CREATED_AT else "",
        ext=ext,
        size=int(doc.FILE_SIZE_BYTES or 0),
        status=doc.PROC_STATUS,
        lastErrorMsg=doc.LAST_ERROR_MSG or "",
        deletedAt=doc.DELETED_AT.isoformat() if doc.DELETED_AT else None,
    )