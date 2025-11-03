# backend/user/db.py
import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv() 

# DB_USER = os.getenv("DB_USER", "mainuser")
# DB_PASS = os.getenv("DB_PASS", "main1234")
# DB_HOST = os.getenv("DB_HOST", "192.168.0.42")
# DB_PORT = os.getenv("DB_PORT", "3306")
# DB_NAME = os.getenv("DB_NAME", "sumflow")

DB_USER = os.getenv("DB_USER", "root")
# DB_PASS = os.getenv("DB_PASS", "root1234")
DB_PASS_RAW = os.getenv("DB_PASS", "MySql@1234") 
DB_PASS = quote_plus(DB_PASS_RAW)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "sumflow")

DATABASE_URL = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    echo=False,             # SQL 출력 (True로 바꾸면 콘솔에 SQL문 나옴)
    pool_pre_ping=True,     # 연결 유효성 검사
    pool_recycle=3600       # 1시간마다 연결 갱신
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """
    FastAPI에서 의존성 주입으로 DB 세션을 얻을 때 사용.
    예:
        db = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
