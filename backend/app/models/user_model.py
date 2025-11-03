# backend/user/models.py
from sqlalchemy import Column, String, BigInteger, Boolean, DateTime, Date, func
from sqlalchemy.orm import declarative_base, relationship
from core.db import Base

class AppUser(Base):
    """
    APP_USER 테이블 ORM 매핑 클래스
    """
    __tablename__ = "APP_USER"

    USER_ID = Column(BigInteger, primary_key=True, autoincrement=True, comment="사용자 고유 ID")
    LOGIN_ID = Column(String(50), nullable=False, unique=True, comment="로그인 ID")
    PASSWORD_HASH = Column(String(255), nullable=False, comment="비밀번호 해시 (bcrypt/scrypt 저장)")
    NAME = Column(String(100), nullable=False, comment="사용자 이름")
    EMAIL = Column(String(254), nullable=False, unique=True, comment="이메일 주소")
    PHONE_NUMBER = Column(String(30), nullable=True, comment="전화번호")
    NICKNAME = Column(String(100), nullable=True, comment="닉네임")
    ADDRESS_LINE1 = Column(String(200), nullable=True, comment="기본 주소")
    ADDRESS_LINE2 = Column(String(200), nullable=True, comment="상세 주소")
    POSTAL_CODE = Column(String(20), nullable=True, comment="우편번호")
    BIRTH_DATE = Column(Date, nullable=True, comment="생년월일")
    IS_ADMIN = Column(Boolean, nullable=False, server_default="0", comment="관리자 여부")
    STATUS = Column(String(20), nullable=False, server_default="ACTIVE", comment="계정 상태")
    LAST_LOGIN_AT = Column(DateTime, nullable=True, comment="마지막 로그인 시각")
    CREATED_AT = Column(DateTime,nullable=False,server_default=func.current_timestamp(),comment="생성 일시",)
    UPDATED_AT = Column(DateTime,nullable=False,server_default=func.current_timestamp(),onupdate=func.current_timestamp(),comment="수정 일시",)
    DELETED_AT = Column(DateTime,nullable=True,server_default=None,comment="삭제 일시 (NULL이면 삭제되지 않음)",)

    documents = relationship(
        "Document",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Document.OWNER_USER_ID",
    )

    visit_logs = relationship(
        "VisitLog",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="VisitLog.USER_ID",
    )

    def __repr__(self):
        return (
            f"<AppUser(USER_ID={self.USER_ID}, "
            f"LOGIN_ID='{self.LOGIN_ID}', EMAIL='{self.EMAIL}')>"
        )
