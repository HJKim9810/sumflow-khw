from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String, Text, ForeignKey,
    DateTime, Enum, func, text, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker
try:
    from app.core.config import DB_URL
except Exception:
    try:
        from core.config import DB_URL
    except Exception:
        import os
        DB_URL = os.getenv("DB_URL")

Base = declarative_base()
engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
SessionLocal = sessionmaker(bind=engine) if DB_URL else None


class Document(Base):
    __tablename__ = "DOCUMENT"

    DOCUMENT_ID = Column(BigInteger().with_variant(Integer, "sqlite"),
                         primary_key=True, autoincrement=True, comment="문서 고유 ID")

    OWNER_USER_ID = Column(BigInteger().with_variant(Integer, "sqlite"),
                           ForeignKey("APP_USER.USER_ID", ondelete="RESTRICT"),
                           nullable=False, comment="문서 소유자 ID")

    # 결과/배치 식별자
    RESULT_FOLDER_ID = Column(String(100), nullable=False, comment="결과 폴더 ID (outputs/<id>)")
    BATCH_ID = Column(String(64), nullable=True, comment="업로드 배치 식별자")

    # 파일 메타
    ORIGINAL_FILENAME = Column(String(255), nullable=False, comment="원본 파일명")
    CHANGED_FILENAME  = Column(String(255), nullable=True,  comment="변경된 파일명")
    FILE_SIZE_BYTES   = Column(BigInteger().with_variant(Integer, "sqlite"),
                               nullable=False, comment="파일 크기 (bytes)")

    # 분류/제목/요약
    CATEGORY_NAME = Column(String(100),  nullable=True, comment="문서 카테고리 (대/소)")
    TITLE         = Column(String(500),  nullable=True, comment="문서 제목")
    LLM_SUMMARY_TEXT = Column(Text,      nullable=True, comment="요약 텍스트 (LLM 결과)")

    # 요약/메타 경로(파일 상대경로만 관리)
    SUMMARY_TXT_RELPATH    = Column(String(1024), nullable=True, comment="요약 파일 경로 (예: llm/summary.txt)")
    METADATA_JSON_RELPATH  = Column(String(1024), nullable=True, comment="메타데이터 JSON 경로 (예: meta.json)")

    # 상태/에러
    PROC_STATUS   = Column(Enum("OCR_DONE", "SUMM_DONE", "READY", "FAILED", "DELETED",
                                name="proc_status_enum"),
                           nullable=False, server_default=text("'OCR_DONE'"),
                           comment="문서 처리 상태")
    LAST_ERROR_MSG = Column(String(1000), nullable=True, comment="마지막 오류 메시지")

    # 타임스탬프
    CREATED_AT = Column(DateTime(timezone=False), nullable=False,
                        server_default=func.current_timestamp(), comment="생성 일시")
    UPDATED_AT = Column(DateTime(timezone=False), nullable=False,
                        server_default=func.current_timestamp(),
                        onupdate=func.current_timestamp(), comment="수정 일시")
    DELETED_AT = Column(DateTime(timezone=False), nullable=True, server_default=None, comment="삭제 일시")

    __table_args__ = (
        UniqueConstraint("RESULT_FOLDER_ID", name="uq_document_result_folder"),
        Index("ix_document_owner", "OWNER_USER_ID"),
        Index("ix_document_category", "CATEGORY_NAME"),
        Index("ix_document_status", "PROC_STATUS"),
        Index("ix_document_created", "CREATED_AT"),
        Index("ix_document_batch", "BATCH_ID"),
    )


def ensure_schema():
    """DDL과 모델 싱크(로컬 개발 편의). 운영에선 마이그레이션 툴 권장."""
    if engine:
        Base.metadata.create_all(engine)


def insert_or_update_doc(*,
                         owner_user_id: int,
                         result_folder_id: str,
                         original_filename: str,
                         changed_filename: str | None = None,
                         file_size: int = 0,
                         category_name: str | None = None,
                         title: str | None = None,
                         summary_text: str | None = None,
                         summary_relpath: str | None = "llm/summary.txt",
                         meta_relpath: str | None = "meta.json",
                         proc_status: str = "OCR_DONE",
                         last_error: str | None = None,
                         batch_id: str | None = None):
    """
    RESULT_FOLDER_ID 기준 upsert.
    - OCR 직후: proc_status='OCR_DONE', summary_text=None
    - 요약 완료: proc_status='SUMM_DONE' 또는 'READY', summary_text 채움
    - 실패: proc_status='FAILED', last_error 채움
    """
    if not engine:
        return

    with SessionLocal() as ss:
        doc = ss.query(Document).filter(Document.RESULT_FOLDER_ID == result_folder_id).first()

        if not doc:
            doc = Document(
                OWNER_USER_ID=owner_user_id,
                RESULT_FOLDER_ID=result_folder_id,
                BATCH_ID=batch_id,
                ORIGINAL_FILENAME=original_filename,
                CHANGED_FILENAME=changed_filename,
                FILE_SIZE_BYTES=file_size,
                CATEGORY_NAME=category_name,
                TITLE=title,
                LLM_SUMMARY_TEXT=summary_text,
                SUMMARY_TXT_RELPATH=summary_relpath,
                METADATA_JSON_RELPATH=meta_relpath,
                PROC_STATUS=proc_status,
                LAST_ERROR_MSG=last_error,
            )
            ss.add(doc)
        else:
            # 갱신 필드만 신중히 업데이트
            if batch_id is not None:
                doc.BATCH_ID = batch_id
            doc.ORIGINAL_FILENAME = original_filename or doc.ORIGINAL_FILENAME
            doc.CHANGED_FILENAME  = changed_filename if changed_filename is not None else doc.CHANGED_FILENAME
            doc.FILE_SIZE_BYTES   = file_size or doc.FILE_SIZE_BYTES
            doc.CATEGORY_NAME     = category_name if category_name is not None else doc.CATEGORY_NAME
            doc.TITLE             = title if title is not None else doc.TITLE
            if summary_text is not None:
                doc.LLM_SUMMARY_TEXT = summary_text
            if summary_relpath is not None:
                doc.SUMMARY_TXT_RELPATH = summary_relpath
            if meta_relpath is not None:
                doc.METADATA_JSON_RELPATH = meta_relpath
            if proc_status:
                doc.PROC_STATUS = proc_status
            doc.LAST_ERROR_MSG = last_error

        ss.commit()

# --- legacy 호환 upsert 별칭 ---
def upsert_document(**kwargs):
    """
    레거시 호출 호환:
      - rel_meta_json     -> meta_relpath
      - rel_summary_dir   -> summary_relpath (자동으로 '.../summary.txt' 붙임)
      - proc_status='DONE' -> 'OCR_DONE' 또는 'SUMM_DONE'(summary_text 유무로 판별)
    나머지 키는 insert_or_update_doc 그대로 위임.
    """
    # 1) 경로 파라미터 호환
    if "rel_meta_json" in kwargs and "meta_relpath" not in kwargs:
        kwargs["meta_relpath"] = kwargs.pop("rel_meta_json")

    if "rel_summary_dir" in kwargs and "summary_relpath" not in kwargs:
        _dir = (kwargs.pop("rel_summary_dir") or "").rstrip("/\\")
        # 관례상 요약 파일명은 summary.txt
        kwargs["summary_relpath"] = (_dir + "/summary.txt") if _dir else "llm/summary.txt"

    # 2) 상태값 정규화
    ps = kwargs.get("proc_status")
    if ps == "DONE":
        # summary_text 있으면 요약 완료, 없으면 OCR 완료로 간주
        kwargs["proc_status"] = "SUMM_DONE" if kwargs.get("summary_text") else "OCR_DONE"

    # 안전장치: enum 허용값 외가 들어오면 기본값으로
    allowed = {"OCR_DONE", "SUMM_DONE", "READY", "FAILED", "DELETED"}
    if kwargs.get("proc_status") not in allowed:
        kwargs["proc_status"] = "OCR_DONE"

    return insert_or_update_doc(**kwargs)