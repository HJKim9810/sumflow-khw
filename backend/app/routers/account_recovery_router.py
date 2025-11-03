from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func
import bcrypt

from core.db import get_db
from models.user_model import AppUser
from models.email_verification_model import EmailVerification

router = APIRouter(prefix="/api/v1/user", tags=["User"])

class FindIdRequest(BaseModel):
    email: EmailStr

class ResetPwRequest(BaseModel):
    email: EmailStr
    new_password: str

def _mask_login_id(login_id: str) -> str:
    if not login_id:
        return ""
    if len(login_id) <= 3:
        return login_id[0] + "*"*(len(login_id)-1)
    return login_id[:2] + "*"*(len(login_id)-3) + login_id[-1]

def _ensure_verified(db: Session, email: str, purpose: str):
    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.EMAIL == email,
            EmailVerification.PURPOSE == purpose,
            EmailVerification.IS_USED == True,  # 이미 성공 처리된 최신 건
        )
        .order_by(EmailVerification.VERIF_ID.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="이메일 인증이 완료되지 않았습니다.")

@router.post("/find-id")
def find_id(payload: FindIdRequest, db: Session = Depends(get_db)):
    # 1) FIND_ID 인증 완료 확인
    _ensure_verified(db, payload.email, "FIND_ID")

    # 2) 이메일로 가입된 계정들 조회
    users = (
        db.query(AppUser)
        .filter(func.lower(AppUser.EMAIL) == func.lower(payload.email))
        .all()
    )
    if not users:
        # 보안상 200 반환 + 빈 목록 권장(정보 유출 방지). 필요시 404로 바꿔도 됨
        return {"success": True, "login_ids": []}

    masked = [_mask_login_id(u.LOGIN_ID) for u in users]
    return {"success": True, "login_ids": masked}

@router.post("/reset-password")
def reset_password(payload: ResetPwRequest, db: Session = Depends(get_db)):
    # 1) RESET_PW 인증 완료 확인
    _ensure_verified(db, payload.email, "RESET_PASSWORD")

    # 2) 해당 이메일 계정들(여러 개일 수 있음) 중에서
    user = (
        db.query(AppUser)
        .filter(func.lower(AppUser.EMAIL) == func.lower(payload.email))
        .first()
    )
    if not user:
        return {"success": True}

    # 3) 비밀번호 업데이트
    hashed = bcrypt.hashpw(payload.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user.PASSWORD_HASH = hashed
    db.add(user)
    db.commit()
    return {"success": True}