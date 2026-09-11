"""SQLite 数据库连接配置。"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./contests.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_migrations():
    """对已有 SQLite 库做增量加列（create_all 不会修改已存在的表）。"""
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(contests)"))}
        if "contests" not in {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}:
            return
        if "recommended_majors" not in cols:
            conn.execute(text("ALTER TABLE contests ADD COLUMN recommended_majors TEXT DEFAULT '[]'"))
        if "recommended_major_reason" not in cols:
            conn.execute(text("ALTER TABLE contests ADD COLUMN recommended_major_reason TEXT"))


def init_db():
    """建表、增量迁移并写入示例数据（首次启动时调用）。"""
    from . import models, sample_data  # noqa: WPS433
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    sample_data.seed_if_empty()
