import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func
import datetime

# 환경 변수에서 데이터베이스 URL 가져오기
# 설정되지 않은 경우 runtime_data 폴더의 sqlite db를 기본값으로 사용
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///runtime_data/migration.db")

# 데이터베이스 엔진 생성
# `connect_args`는 다중 스레드 접근을 허용하기 위한 SQLite 전용 설정
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 설정된 "Session" 클래스 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모델들을 위한 기본 클래스 생성
Base = declarative_base()

class MigrationJob(Base):
    """
    각 마이그레이션 작업을 저장하는 테이블.
    """
    __tablename__ = "migration_jobs"

    id = Column(Integer, primary_key=True, index=True)
    source_root_page_id = Column(String, nullable=False)
    target_root_page_id = Column(String, nullable=False)
    status = Column(String, default="PENDING") # 상태: PENDING, RUNNING, COMPLETED, FAILED
    total_pages = Column(Integer, default=0)
    successful_pages = Column(Integer, default=0)
    failed_pages = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # PageMapping과의 관계 설정
    pages = relationship("PageMapping", back_populates="job")

class PageMapping(Base):
    """
    소스 페이지 ID와 타겟 페이지 ID를 매핑하는 테이블.
    마이그레이션 상태와 에러 메시지도 포함.
    """
    __tablename__ = "page_mappings"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("migration_jobs.id"), nullable=False)
    source_page_id = Column(String, nullable=False)
    source_page_title = Column(String, nullable=False)
    source_parent_id = Column(String, nullable=True)
    target_page_id = Column(String, nullable=True)
    target_parent_id = Column(String, nullable=True)
    status = Column(String, default="PENDING") # 상태: PENDING, SUCCESS, FAILED, SKIPPED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # MigrationJob과의 관계 설정
    job = relationship("MigrationJob", back_populates="pages")


class ValidationJob(Base):
    """
    검증 작업의 결과를 저장하는 테이블.
    """
    __tablename__ = "validation_jobs"
    id = Column(Integer, primary_key=True, index=True)
    migration_job_id = Column(Integer, ForeignKey('migration_jobs.id'))
    source_root_page_id = Column(String, nullable=False)
    target_root_page_id = Column(String, nullable=False)
    status = Column(String, default="PENDING") # 상태: PENDING, RUNNING, COMPLETED
    missing_pages_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ValidationResult(Base):
    """
    검증 작업에서 발견된 개별 불일치 항목을 저장하는 테이블.
    """
    __tablename__ = "validation_results"
    id = Column(Integer, primary_key=True, index=True)
    validation_job_id = Column(Integer, ForeignKey('validation_jobs.id'))
    source_page_id = Column(String)
    source_page_title = Column(String)
    reason = Column(String) # 예: "타겟에서 페이지를 찾을 수 없음", "상위 페이지 불일치"


def get_db():
    """
    데이터베이스 세션을 가져오는 의존성 함수.
    요청 처리 후 세션이 항상 닫히도록 보장.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """
    데이터베이스를 초기화하고 테이블이 없으면 생성.
    """
    # runtime_data 디렉토리가 없으면 생성
    db_file_path = DATABASE_URL.split("///")[-1]
    db_dir = os.path.dirname(db_file_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    Base.metadata.create_all(bind=engine)
    print("데이터베이스가 초기화되었습니다.")

if __name__ == "__main__":
    # 이 스크립트를 직접 실행하여 DB를 초기화할 수 있음
    init_db()
