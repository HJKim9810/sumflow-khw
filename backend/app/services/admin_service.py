from datetime import datetime, timedelta
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, case, and_

from models.user_model import AppUser
from models.document_model import Document
from models.visitlog_model import VisitLog
from schemas.admin_schema import AdminStatsSummary, DailyUploadStat, DailyVisitStat

def get_admin_stats_summary(db: Session) -> AdminStatsSummary:
    now = datetime.now()
    since_7d = now - timedelta(days=6)   # 오늘 포함 최근 7일
    since_30d = now - timedelta(days=30) # 최근 30일

    # -------------------------
    # 총 회원수
    # -------------------------
    total_users = db.query(func.count(AppUser.id)).scalar() or 0

    # -------------------------
    # 최근 30일 신규 가입
    # -------------------------
    new_users_30d = (
        db.query(func.count(AppUser.id))
        .filter(AppUser.created_at >= since_30d)
        .filter(AppUser.status == "ACTIVE")  # 가입한 상태가 ACTIVE
        .scalar()
        or 0
    )

    # -------------------------
    # 최근 30일 탈퇴
    # -------------------------
    withdraw_30d = (
        db.query(func.count(AppUser.id))
        .filter(AppUser.updated_at >= since_30d)
        .filter(AppUser.status == "WITHDRAWN")
        .scalar()
        or 0
    )

    # -------------------------
    # 최근 7일 업로드 수 (문서 등록 수)
    # group by day (MM/DD)
    # -------------------------
    upload_rows = (
        db.query(
            func.date_format(Document.CREATED_AT, "%m/%d").label("day"),
            func.count(Document.DOCUMENT_ID).label("uploads"),
        )
        .filter(Document.CREATED_AT >= since_7d)
        .group_by(func.date_format(Document.CREATED_AT, "%m/%d"))
        .order_by(func.date_format(Document.CREATED_AT, "%m/%d"))
        .all()
    )
    day_to_uploads = {row.day: row.uploads for row in upload_rows}

    # -------------------------
    # 최근 7일 방문수 (visit log)
    # -------------------------
    visit_rows = (
        db.query(
            func.to_char(VisitLog.created_at, "MM/DD").label("day"),
            func.count(VisitLog.id).label("visits"),
        )
        .filter(VisitLog.created_at >= since_7d)
        .group_by(func.to_char(VisitLog.created_at, "MM/DD"))
        .order_by(func.min(VisitLog.created_at))
        .all()
    )
    day_to_visits = {row.day: row.visits for row in visit_rows}

    # -------------------------
    # 7일치 라벨을 무조건 만들어서 비어 있는 날도 0으로 채워주자
    # -------------------------
    days_7 = []
    for i in range(7):
        d = since_7d + timedelta(days=i)
        days_7.append(d.strftime("%m/%d"))

    daily_uploads7d = [
        DailyUploadStat(day=day, uploads=int(day_to_uploads.get(day, 0)))
        for day in days_7
    ]
    daily_visits7d = [
        DailyVisitStat(day=day, visits=int(day_to_visits.get(day, 0)))
        for day in days_7
    ]

    return AdminStatsSummary(
        totalUsers=int(total_users),
        newUsers30d=int(new_users_30d),
        withdraw30d=int(withdraw_30d),
        dailyUploads7d=daily_uploads7d,
        dailyVisits7d=daily_visits7d,
    )

def list_files_service(
    db: Session,
    nickname: str = "",
    filename: str = "",
    ocr_status: str = "",
    page: int = 1,
    page_size: int = 10,
):
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 10)))

    U = aliased(AppUser)
    # 기준 쿼리: 닉네임/파일명만 반영 (상태/페이지 제외)
    QB = (
        db.query(
            Document.DOCUMENT_ID.label("id"),
            U.NICKNAME.label("nickname"),
            Document.ORIGINAL_FILENAME.label("filename"),
            Document.CREATED_AT.label("uploadedAt"),
            Document.FILE_SIZE_BYTES.label("size"),
            Document.PROC_STATUS.label("status"),
            Document.LAST_ERROR_MSG.label("lastErrorMsg"),
            Document.DELETED_AT.label("deletedAt"),
        )
        .join(U, U.USER_ID == Document.OWNER_USER_ID)
    )

    base_conds = []
    if nickname:
        base_conds.append(func.lower(U.NICKNAME).like(f"%{nickname.lower()}%"))
    if filename:
        base_conds.append(func.lower(Document.ORIGINAL_FILENAME).like(f"%{filename.lower()}%"))
    if base_conds:
        QB = QB.filter(and_(*base_conds))

    all_count   = QB.filter(Document.PROC_STATUS.in_(("DONE","FAILED"))).count()
    done_count  = QB.filter(Document.PROC_STATUS == "DONE").count()
    failed_count= QB.filter(Document.PROC_STATUS == "FAILED").count()

    Q = QB
    if ocr_status in ("DONE", "FAILED", "DELETED"):
        Q = Q.filter(Document.PROC_STATUS == ocr_status)

    total = Q.count()

    rows = (
        Q.order_by(Document.CREATED_AT.desc())
         .offset((page - 1) * page_size)
         .limit(page_size)
         .all()
    )

    items = []
    for r in rows:
        ext = ""
        if r.filename and "." in r.filename:
            ext = r.filename.rsplit(".", 1)[-1].lower()
        items.append({
            "id": r.id,
            "nickname": r.nickname or "-",
            "filename": r.filename or "-",
            "uploadedAt": r.uploadedAt.isoformat() if r.uploadedAt else "",
            "ext": ext,
            "size": int(r.size or 0),
            "status": r.status,
            "lastErrorMsg": r.lastErrorMsg or "",
            "deletedAt": r.deletedAt.isoformat() if r.deletedAt else None,
        })

    return {
        "total": total,
        "items": items,
        "stats": {"all": all_count, "done": done_count, "failed": failed_count},
    }

def soft_delete_document_service(db: Session, document_id: int):
    doc = db.query(Document).filter(Document.DOCUMENT_ID == document_id).first()
    if not doc:
        return None, "NOT_FOUND"

    if doc.PROC_STATUS == "DELETED":
        return doc, "ALREADY_DELETED"

    now = datetime.utcnow()
    doc.PROC_STATUS = "DELETED"
    doc.DELETED_AT = now
    doc.UPDATED_AT = now
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc, "OK"