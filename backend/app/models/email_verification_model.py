from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
)
from core.db import Base  

class EmailVerification(Base):
    __tablename__ = "EMAIL_VERIFICATION"

    VERIF_ID = Column(Integer, primary_key=True, autoincrement=True)
    EMAIL = Column(String(255), nullable=False, index=True)
    CODE = Column(String(20), nullable=False)
    PURPOSE = Column(String(50), nullable=False, default="REGISTER")
    IS_USED = Column(Boolean, nullable=False, default=False)

    EXPIRES_AT = Column(DateTime, nullable=False)
    CREATED_AT = Column(DateTime, nullable=False)