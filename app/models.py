"""SQLAlchemy ORM 模型，字段严格按产品文档第四章定义。"""
from sqlalchemy import Column, String

from .database import Base


class Contest(Base):
    __tablename__ = "contests"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    category = Column(String, default="")
    organizer = Column(String, default="")
    # list[str] 以 JSON 字符串形式存储
    eligible_grades = Column(String, default="[]")
    major_limit = Column(String, default="不限")
    school_limit = Column(String, default="待确认")
    registration_deadline = Column(String, default="")
    submission_deadline = Column(String, default="")
    materials = Column(String, default="")
    skills = Column(String, default="")
    estimated_time = Column(String, default="")
    notice_url = Column(String, default="")
    registration_url = Column(String, default="")
    source_type = Column(String, default="其他")
    verified_at = Column(String, default="")
    status = Column(String, default="待确认")
    review_note = Column(String, default="")
