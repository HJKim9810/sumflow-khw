from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.db import get_db
from models.user_model import AppUser

router = APIRouter(
    prefix="/api/v1/user",
    tags=["User"],
)

@router.get("/check-id")
def check_id(login_id: str = Query(..., min_length=6, max_length=16), db: Session = Depends(get_db)):
    q = login_id.strip()
    if not q:
        raise HTTPException(status_code=400, detail="login_id is required")

    exists = (
        db.query(AppUser.USER_ID)
        .filter(func.lower(AppUser.LOGIN_ID) == q.lower())
        .first()
    )
    return {"isDuplicate": bool(exists)}


@router.get("/check-email")
def check_email(email: str, db: Session = Depends(get_db)):
    """
    이메일(email) 중복 여부 확인
    return:
      "1" -> 이미 사용 중
      "0" -> 사용 가능
    """

    exists = (
        db.query(AppUser)
        .filter(AppUser.EMAIL == email)
        .first()
    )

    return "1" if exists else "0"

@router.get("/check-nickname")
def check_nickname(nickname: str = Query(..., min_length=3, max_length=8), db: Session = Depends(get_db)):
    q = nickname.strip()
    if not q:
        raise HTTPException(400, detail="nickname is required")
    exists = (
        db.query(AppUser.USER_ID)
        .filter(AppUser.NICKNAME.isnot(None))
        .filter(func.lower(AppUser.NICKNAME) == q.lower())
        .first()
    )
    return {"isDuplicate": bool(exists)}