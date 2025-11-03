from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from core.db import get_db
from models.user_model import AppUser
from services.captcha import captcha_store
from services.email_verify import assert_email_verified  
import time, bcrypt
from datetime import datetime

router = APIRouter(prefix="/api/v1/user", tags=["User"])


class SignupRequest(BaseModel):
    login_id: str
    password: str
    name: str
    email: EmailStr
    captcha_id: str
    captcha_text: str

    phone: str | None = None
    nickname: str | None = None
    postal_code: str | None = None
    addr1: str | None = None
    addr2: str | None = None
    birth: str | None = None
    is_admin: bool | None = False


@router.post("/signup")
def signup_user(data: SignupRequest, db: Session = Depends(get_db)):
    # 1) CAPTCHA 검증
    captcha_record = captcha_store.get(data.captcha_id)
    if not captcha_record:
        raise HTTPException(status_code=400, detail="Captcha expired or invalid")

    captcha_code, expire_time = captcha_record
    if time.time() > expire_time:
        del captcha_store[data.captcha_id]
        raise HTTPException(status_code=400, detail="Captcha expired")

    if data.captcha_text.strip().lower() != captcha_code.lower():
        raise HTTPException(status_code=400, detail="Captcha incorrect")

    del captcha_store[data.captcha_id]

    # 2) 이미 가입된 아이디/이메일 여부 확인
    existing_user = (
        db.query(AppUser)
        .filter(
            (AppUser.LOGIN_ID == data.login_id)
            | (AppUser.EMAIL == data.email)
        )
        .first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="ID or Email already exists")

    # ✅ 3) 이메일 인증 성공 여부 확인
    # 여기서 이메일이 "REGISTER" 용도로 verify-code 성공된 상태인지 확인
    assert_email_verified(db, data.email, "REGISTER")

    # 4) 비밀번호 해시
    hashed_pw = bcrypt.hashpw(
        data.password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    # 5) 생년월일 파싱 (YYYYMMDD -> date)
    birth_date = None
    if data.birth:
        try:
            birth_date = datetime.strptime(data.birth, "%Y%m%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid birth date format (YYYYMMDD)")

    # 6) 유저 생성
    new_user = AppUser(
        LOGIN_ID=data.login_id,
        PASSWORD_HASH=hashed_pw,
        NAME=data.name,
        EMAIL=data.email,
        PHONE_NUMBER=data.phone,
        NICKNAME=data.nickname,
        ADDRESS_LINE1=data.addr1,
        ADDRESS_LINE2=data.addr2,
        POSTAL_CODE=data.postal_code,
        BIRTH_DATE=birth_date,
        IS_ADMIN=data.is_admin or False,
        STATUS="ACTIVE",
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "success": True,
        "message": "회원가입 완료",
        "user_id": new_user.USER_ID,
        "login_id": new_user.LOGIN_ID,
    }