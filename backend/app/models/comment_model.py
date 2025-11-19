from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, Text, Boolean, ForeignKey, func
from sqlalchemy.dialects.mysql import DATETIME as MYSQL_DATETIME, LONGTEXT as MYSQL_LONGTEXT
from sqlalchemy.orm import relationship
from app.core.db import Base

# MySQL DATETIME(6) 대응
def DATETIME6():
    return MYSQL_DATETIME(fsp=6)

# MySQL LONGTEXT 대응 (sqlite 등에서는 Text로 fallback)
def LONGTEXT():
    try:
        return MYSQL_LONGTEXT
    except Exception:
        return Text

class DocComment(Base):
    __tablename__ = "DOC_COMMENT"

    COMMENT_ID = Column(BigInteger().with_variant(Integer, "sqlite"),
                        primary_key=True, autoincrement=True, comment="댓글 고유 ID")
    DOCUMENT_ID = Column(BigInteger().with_variant(Integer, "sqlite"),
                         ForeignKey("DOCUMENT.DOCUMENT_ID", ondelete="CASCADE"),
                         nullable=False, comment="문서 ID")
    USER_ID = Column(BigInteger().with_variant(Integer, "sqlite"),
                     ForeignKey("APP_USER.USER_ID", ondelete="CASCADE"),
                     nullable=False, comment="작성자 ID")

    # BODY LONGTEXT
    BODY = Column(LONGTEXT(), nullable=False, comment="댓글 내용")

    IS_DELETED = Column(Boolean, nullable=False, default=False, server_default="0", comment="삭제 여부")

    CREATED_AT = Column(DATETIME6(), nullable=False, server_default=func.now(), comment="생성 일시")
    UPDATED_AT = Column(DATETIME6(), nullable=False, server_default=func.now(),
                        onupdate=func.now(), comment="수정 일시")

    # 선택: 역참조
    document = relationship("Document", backref="doc_comments", lazy="joined")