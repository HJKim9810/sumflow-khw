# backend/user/login.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from core.db import get_db
from core.security import decode_access_token
from models.user_model import AppUser
from services.captcha import captcha_store
import time
import bcrypt
import os, jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/v1/user", tags=["User"])

# ----------------------------------------
# 1️⃣ JWT 설정
# ----------------------------------------
JWT_SECRET = os.getenv("JWT_SECRET", "mysecretkey")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 6  # 6시간

# ----------------------------------------
# 2️⃣ 요청 데이터 모델
# ----------------------------------------
class LoginRequest(BaseModel):
    login_id: str
    password: str
    captcha_id: str
    captcha_text: str

# ----------------------------------------
# 3️⃣ 로그인 엔드포인트
# ----------------------------------------
@router.post("/login")
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    #  CAPTCHA 검증
    record = captcha_store.get(data.captcha_id)
    if not record:
        raise HTTPException(
            status_code=400,
            detail="보안문자 정보가 존재하지 않거나 만료되었습니다. 새로 고침 후 다시 시도해주세요."
        )

    code, expire_time = record
    if time.time() > expire_time:
        del captcha_store[data.captcha_id]
        raise HTTPException(
            status_code=400,
            detail="보안문자 입력 시간이 초과되었습니다. 새로 고침 후 다시 시도해주세요."
        )

    if data.captcha_text.strip().lower() != code.lower():
        raise HTTPException(
            status_code=400,
            detail="보안문자가 올바르지 않습니다. 다시 입력해주세요."
        )

    # 일회성 사용 후 제거
    del captcha_store[data.captcha_id]

    #  사용자 조회
    user = (
        db.query(AppUser)
        .filter(AppUser.LOGIN_ID == data.login_id)
        .first()
    )
    if not user:
        # 계정 유무와 비밀번호 오류는 같은 메시지로 (보안상)
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )

    #  비밀번호 검증
    if not bcrypt.checkpw(
        data.password.encode("utf-8"),
        user.PASSWORD_HASH.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )

    #  마지막 로그인 시간 갱신
    db.query(AppUser).filter(AppUser.USER_ID == user.USER_ID).update(
        {AppUser.LAST_LOGIN_AT: func.now()},
        synchronize_session=False,
    )
    db.commit()

    #  토큰 생성
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user.LOGIN_ID,
        "user_id": int(user.USER_ID),
        "exp": expire,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {
        "success": True,
        "message": "로그인에 성공했습니다.",
        "token": token,
        "user": {
            "id": user.USER_ID,
            "login_id": user.LOGIN_ID,
            "email": user.EMAIL,
            "name": user.NAME,
            "nickname": user.NICKNAME,
            "IS_ADMIN": bool(user.IS_ADMIN),
        },
    }

@router.api_route("/logout", methods=["POST", "GET"])
def logout_user(
    request: Request,
    db: Session = Depends(get_db),
):
    # 1) 식별값 확보
    user_id = None
    login_id = None

    # 1-1) 토큰 시도 (Authorization: Bearer <token>)
    token = None
    auth = request.headers.get("Authorization") or ""
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = request.query_params.get("token")

    if token:
        import os, jwt
        secret = os.getenv("JWT_SECRET", "YOUR_SUPER_SECRET_KEY")
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            user_id = payload.get("user_id")
            login_id = payload.get("sub")
        except Exception:
            pass

    return {"success": True}