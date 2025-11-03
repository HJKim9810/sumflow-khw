import random
import string
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from models.email_verification_model import EmailVerification
from models.user_model import AppUser

import smtplib
from email.mime.text import MIMEText
import os

# -----------------------------
# 공통
# -----------------------------
def _utcnow_naive():
    return datetime.utcnow()

def _gen_code(length=6):
    return "".join(random.choices(string.digits, k=length))

def _subject_body(purpose: str, code: str):
    if purpose == "FIND_ID":
        return "[SumFlow] 아이디 찾기 인증번호", f"아이디 찾기 인증번호: {code}\n1분 안에 입력해주세요."
    if purpose == "RESET_PASSWORD":
        return "[SumFlow] 비밀번호 재설정 인증번호", f"비밀번호 재설정 인증번호: {code}\n1분 안에 입력해주세요."
    # 기본(회원가입)
    return "[SumFlow] 회원가입 이메일 인증번호", f"회원가입 이메일 인증번호: {code}\n1분 안에 입력해주세요."

def send_email(to: str, subject: str, body: str):
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    from_addr = os.getenv("SMTP_FROM", smtp_user or "")

    if not smtp_user or not smtp_pass:
        # 개발 편의: 실제 메일 설정 없으면 콘솔 출력
        print("=== SEND EMAIL (FAKE MODE) ===")
        print("TO:", to)
        print("SUBJECT:", subject)
        print("BODY:", body)
        print("==============================")
        return

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr or smtp_user
    msg["To"] = to

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(msg["From"], [to], msg.as_string())

    print(f"[메일 전송 완료] -> {to}")

# -----------------------------
# 인증 코드 생성/발송
# -----------------------------
def create_and_send_code(db: Session, email: str, purpose: str = "REGISTER"):
    purpose = purpose.upper().strip()

    # 존재 여부 체크
    user_exists = db.query(AppUser).filter(func.lower(AppUser.EMAIL) == func.lower(email)).first() is not None

    if purpose == "REGISTER":
        if user_exists:
            raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")
    elif purpose in ("FIND_ID", "RESET_PASSWORD", "EMAIL_UPDATE"):
        if not user_exists:
            raise HTTPException(status_code=404, detail="가입되지 않은 이메일입니다.")
    else:
        raise HTTPException(status_code=400, detail="허용되지 않은 purpose 입니다.")

    # (선택) 최근 발송 Rate Limit (예: 60초)
    last = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.EMAIL == email,
            EmailVerification.PURPOSE == purpose,
        )
        .order_by(EmailVerification.VERIF_ID.desc())
        .first()
    )
    now = _utcnow_naive()
    if last and last.CREATED_AT and (now - last.CREATED_AT).total_seconds() < 60:
        raise HTTPException(status_code=429, detail="인증번호를 60초 후 다시 요청하세요.")

    code = _gen_code(6)
    expires_at = now + timedelta(minutes=10)

    row = EmailVerification(
        EMAIL=email,
        CODE=code,
        PURPOSE=purpose,
        IS_USED=False,
        EXPIRES_AT=expires_at,
        CREATED_AT=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    subject, body = _subject_body(purpose, code)
    send_email(to=email, subject=subject, body=body)

    return {"success": True}

# -----------------------------
# 인증 코드 검증
# -----------------------------
def verify_code(db: Session, email: str, code: str, purpose: str = "REGISTER"):
    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.EMAIL == email,
            EmailVerification.PURPOSE == purpose,
        )
        .order_by(EmailVerification.VERIF_ID.desc())
        .first()
    )

    if not row:
        raise HTTPException(status_code=400, detail="인증 기록이 없습니다.")

    now = _utcnow_naive()
    row_expires = row.EXPIRES_AT.replace(tzinfo=None) if getattr(row.EXPIRES_AT, "tzinfo", None) else row.EXPIRES_AT
    if row_expires and now > row_expires:
        raise HTTPException(status_code=400, detail="인증번호가 만료되었습니다.")

    if row.IS_USED:
        raise HTTPException(status_code=400, detail="이미 사용된 인증번호입니다.")

    if row.CODE != code:
        raise HTTPException(status_code=400, detail="인증번호가 올바르지 않습니다.")

    row.IS_USED = True
    db.commit()
    return {"success": True}

# -----------------------------
# 회원가입 직전 보증
# -----------------------------
def assert_email_verified(db: Session, email: str, purpose: str = "REGISTER"):
    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.EMAIL == email,
            EmailVerification.PURPOSE == purpose,
            EmailVerification.IS_USED == True,
        )
        .order_by(EmailVerification.VERIF_ID.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="이메일 인증이 완료되지 않았습니다.")