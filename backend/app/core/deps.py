from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from .db import get_db
from .security import decode_access_token  # JWT 파싱 함수 (예상)
from models.user_model import AppUser

def get_current_user(
    db: Session = Depends(get_db),
    token_data: dict = Depends(decode_access_token),
):
    """
    decode_access_token() 이
    - Authorization: Bearer ... 에서 토큰 뽑고
    - 유효성 검사 후 { "user_id": ..., ... } 형태 리턴한다고 가정
    """
    user_id = token_data.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: no user id",
        )

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if user.status == "WITHDRAWN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User withdrawn",
        )

    return user

def get_current_admin(
    current_user: AppUser = Depends(get_current_user),
):
    """
    관리자 여부 확인.
    AppUser에 is_admin (BOOLEAN or 'Y'/'N') 있다고 가정.
    """
    is_admin = False
    # 예: 컬럼이 Boolean이면:
    # is_admin = bool(current_user.is_admin)
    # 예: 컬럼이 'Y'/'N'이면:
    if hasattr(current_user, "is_admin"):
        v = getattr(current_user, "is_admin")
        if isinstance(v, bool):
            is_admin = v
        else:
            # 문자열 기반이라면
            is_admin = (str(v).upper() == "Y")

    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privilege required",
        )

    return current_user