# app/services/db_service.py

from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String, Text, ForeignKey,
    DateTime, Enum, func, text, UniqueConstraint, Index, inspect
)
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DATABASE_URL

# ----- Base 선언 -----
Base = declarative_base()

# ----- 내부 상태(지연 초기화) -----
_engine = None
_SessionLocal = None
class AppUser(Base):
    __tablename__ = "APP_USER"  # ← FK 문자열과 정확히 동일하게
    USER_ID = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="사용자 PK"
    )

def ensure_schema():
    if engine:
        insp = inspect(engine)
        # DOCUMENT만 없으면 생성 (APP_USER는 FK 타겟이므로 선행 존재 필요)
        if not insp.has_table("DOCUMENT"):
            Base.metadata.create_all(engine, tables=[Document.__table__])

def get_engine():
    """
    lazy-init 엔진 생성. 외부에서 import 시에도 안전하게 사용 가능.
    """
    global _engine, _SessionLocal
    if _engine is None:
        try:
            _engine = create_engine(DATABASE_URL, pool_pre_ping=True)
            _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
            print("[DB] Engine successfully initialized.")
        except Exception as e:
            print(f"[DB] Engine init failed: {e}")
            _engine = None
    return _engine

def get_session_factory():
    """
    sessionmaker 반환. 없으면 엔진부터 초기화.
    """
    global _SessionLocal
    if _SessionLocal is None:
        eng = get_engine()
        if eng is None:
            return None
        # _SessionLocal 은 get_engine()에서 이미 세팅됨. 방어차원 재확인.
        if _SessionLocal is None:
            _SessionLocal = sessionmaker(bind=eng, autoflush=False, autocommit=False)
    return _SessionLocal

def get_session():
    """
    실제 Session 인스턴스 1개를 반환.
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("[DB] No session available (engine init failed)")
    return factory()

# ----- 외부 모듈 호환용 공개 심볼 -----
# 다른 모듈에서 `from app.services.db_service import engine, SessionLocal` 로 가져가도록 보장
engine = get_engine()                    # Engine or None
SessionLocal = get_session_factory()     # sessionmaker or None

# ----- 모델 -----
class Document(Base):
    __tablename__ = "DOCUMENT"

    DOCUMENT_ID = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True, comment="문서 고유 ID"
    )

    OWNER_USER_ID = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("APP_USER.USER_ID", ondelete="RESTRICT"),
        nullable=False, comment="문서 소유자 ID"
    )

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
    PROC_STATUS   = Column(
        Enum("OCR_DONE", "SUMM_DONE", "READY", "FAILED", "DELETED", name="proc_status_enum"),
        nullable=False, server_default=text("'OCR_DONE'"),
        comment="문서 처리 상태"
    )
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

# ----- 유틸 -----
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
                         llm_summary_text: str | None = None,
                         batch_id: str | None = None):
    """
    RESULT_FOLDER_ID 기준 upsert.
    - OCR 직후: proc_status='OCR_DONE', summary_text=None
    - 요약 완료: proc_status='SUMM_DONE' 또는 'READY', summary_text 채움
    - 실패: proc_status='FAILED', last_error 채움
    """
    if engine is None:
        # 엔진 초기화 재시도
        _ = get_engine()
        if _ is None:
            return

    factory = get_session_factory()
    if factory is None:
        return

    with factory() as ss:
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
                LLM_SUMMARY_TEXT=llm_summary_text or summary_text,
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
            if original_filename:
                doc.ORIGINAL_FILENAME = original_filename
            if changed_filename is not None:
                doc.CHANGED_FILENAME = changed_filename
            if file_size:
                doc.FILE_SIZE_BYTES = file_size
            if category_name is not None:
                doc.CATEGORY_NAME = category_name
            if title is not None:
                doc.TITLE = title
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
        kwargs["summary_relpath"] = (_dir + "/summary.txt") if _dir else "llm/summary.txt"
    
    if "rel_summary_txt" in kwargs and "summary_relpath" not in kwargs:
        kwargs["summary_relpath"] = kwargs.pop("rel_summary_txt")

    # 2) 상태값 정규화
    ps = kwargs.get("proc_status")
    if ps == "DONE":
        kwargs["proc_status"] = "SUMM_DONE" if kwargs.get("summary_text") else "OCR_DONE"

    # 안전장치: enum 허용값 외가 들어오면 기본값으로
    allowed = {"OCR_DONE", "SUMM_DONE", "READY", "FAILED", "DELETED"}
    if kwargs.get("proc_status") not in allowed:
        kwargs["proc_status"] = "OCR_DONE"

    return insert_or_update_doc(**kwargs)
