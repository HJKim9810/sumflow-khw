from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    Enum,
    ForeignKey,
    func,
    text,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import relationship
from core.db import Base

class Document(Base):
    __tablename__ = "DOCUMENT"

    # -------------------------
    # PK
    # -------------------------
    DOCUMENT_ID = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="문서 고유 ID",
    )

    # -------------------------
    # 소유자
    # -------------------------
    OWNER_USER_ID = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("APP_USER.USER_ID", ondelete="RESTRICT"),
        nullable=False,
        comment="문서 소유자 ID",
    )

    # -------------------------
    # 결과/배치 식별자
    # -------------------------
    RESULT_FOLDER_ID = Column(
        String(100),
        nullable=False,  # ✅ NOT NULL
        comment="결과 폴더 ID (outputs/<id>)",
    )

    BATCH_ID = Column(
        String(64),
        nullable=True,
        comment="업로드 배치 식별자(Zip 묶음 기준)",
    )

    # -------------------------
    # 파일 메타
    # -------------------------
    ORIGINAL_FILENAME = Column(String(255), nullable=False, comment="원본 파일명")
    CHANGED_FILENAME = Column(String(255), nullable=True, comment="변경된 파일명")
    FILE_SIZE_BYTES = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=False,
        comment="파일 크기 (bytes)",
    )

    # -------------------------
    # 분류/제목/요약(텍스트)
    # -------------------------
    CATEGORY_NAME = Column(String(100), nullable=True, comment="문서 카테고리 (대/소)")
    TITLE = Column(String(500), nullable=True, comment="문서 제목")

    LLM_SUMMARY_TEXT = Column(Text, nullable=True, comment="요약 텍스트 (LLM 결과)")
    SUMMARY_TXT_RELPATH = Column(
        String(1024),
        nullable=True,
        comment="요약 파일 경로 (예: llm/summary.txt)",
    )
    METADATA_JSON_RELPATH = Column(
        String(1024),
        nullable=True,
        comment="메타데이터 JSON 경로 (예: meta.json)",
    )

    # ✅ 중간 산출물 보관 안 하므로 제거됨:
    # OCR_JSON_DIR_RELPATH, OCR_TEXT_DIR_RELPATH, MERGED_PDF_RELPATH

    # -------------------------
    # 처리 상태
    # -------------------------
    PROC_STATUS = Column(
        Enum(
            "OCR_DONE",
            "SUMM_DONE",
            "READY",
            "FAILED",
            "DELETED",
            name="proc_status_enum",
        ),
        nullable=False,
        server_default=text("'OCR_DONE'"),
        comment="문서 처리 상태",
    )

    LAST_ERROR_MSG = Column(String(1000), nullable=True, comment="마지막 오류 메시지")

    # -------------------------
    # 타임스탬프
    # -------------------------
    CREATED_AT = Column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=func.current_timestamp(),
        comment="생성 일시",
    )
    UPDATED_AT = Column(
        DATETIME(fsp=6),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        comment="수정 일시",
    )
    DELETED_AT = Column(
        DATETIME(fsp=6),
        nullable=True,
        server_default=None,
        comment="삭제 일시",
    )

    # -------------------------
    # 관계
    # -------------------------
    user = relationship(
        "AppUser",
        back_populates="documents",
        foreign_keys=[OWNER_USER_ID],
        passive_deletes=True,
    )

    # -------------------------
    # 테이블 옵션(인덱스/제약)
    # -------------------------
    __table_args__ = (
        UniqueConstraint("RESULT_FOLDER_ID", name="uq_document_result_folder"),
        Index("ix_document_owner", "OWNER_USER_ID"),
        Index("ix_document_category", "CATEGORY_NAME"),
        Index("ix_document_status", "PROC_STATUS"),
        Index("ix_document_created", "CREATED_AT"),
        Index("ix_document_batch", "BATCH_ID"),
    )

    def __repr__(self):
        return (
            f"<Document DOCUMENT_ID={self.DOCUMENT_ID} "
            f"OWNER={self.OWNER_USER_ID} "
            f"FOLDER={self.RESULT_FOLDER_ID} "
            f"STATUS={self.PROC_STATUS}>"
        )