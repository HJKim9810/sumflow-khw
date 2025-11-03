from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from core.db import get_db
from services.email_verify import create_and_send_code, verify_code

router = APIRouter(
    prefix="/api/v1/user",
    tags=["User"],
)


# ------------------------------
# 요청 스키마
# ------------------------------
class SendCodeRequest(BaseModel):
    email: EmailStr
    purpose: str  # REGISTER | FIND_ID | RESET_PW


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str
    purpose: str  # REGISTER | FIND_ID | RESET_PW


# ------------------------------
# 이메일 코드 발송
# ------------------------------
@router.post("/email/send-code")
def send_code(data: SendCodeRequest, db: Session = Depends(get_db)):
    """
    이메일 인증 코드 발송 (회원가입/아이디찾기/비밀번호찾기 공용)
    purpose:
      - REGISTER : 신규 가입용
      - FIND_ID  : 아이디 찾기용
      - RESET_PW : 비밀번호 재설정용
    """
    purpose = data.purpose.upper().strip()
    if purpose not in ("REGISTER", "FIND_ID", "RESET_PASSWORD"):
        raise HTTPException(status_code=400, detail="허용되지 않은 purpose 값입니다.")

    result = create_and_send_code(db, data.email, purpose)
    return {"success": True, "purpose": purpose, **result}


# ------------------------------
# 이메일 코드 검증
# ------------------------------
@router.post("/email/verify-code")
def check_code(data: VerifyCodeRequest, db: Session = Depends(get_db)):
    """
    이메일 인증 코드 검증 (회원가입/아이디찾기/비밀번호찾기 공용)
    """
    purpose = data.purpose.upper().strip()
    if purpose not in ("REGISTER", "FIND_ID", "RESET_PASSWORD"):
        raise HTTPException(status_code=400, detail="허용되지 않은 purpose 값입니다.")

    result = verify_code(db, data.email, data.code, purpose)
    return {"success": True, "purpose": purpose, **result}