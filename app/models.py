"""SQLAlchemy ORM 模型。

字段对齐：产品文档第四章 + 连诗钰《V1 字段映射与交接》前端契约
（session/tags/process/outcomes/link_status）。
list/dict 字段以 JSON 字符串形式存储。
"""
from sqlalchemy import Column, String

from .database import Base


class Contest(Base):
    __tablename__ = "contests"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    session = Column(String, default="")
    category = Column(String, default="")
    tags = Column(String, default="[]")
    organizer = Column(String, default="")
    eligible_grades = Column(String, default="[]")
    major_limit = Column(String, default="不限")
    school_limit = Column(String, default="待确认")
    registration_deadline = Column(String, default="")
    registration_deadline_note = Column(String, default="")
    submission_deadline = Column(String, default="")
    submission_deadline_note = Column(String, default="")
    materials = Column(String, default="")
    process = Column(String, default="")
    skills = Column(String, default="")
    outcomes = Column(String, default="")
    ability_training = Column(String, default="")
    estimated_time = Column(String, default="")
    notice_url = Column(String, default="")
    registration_url = Column(String, default="")
    source_type = Column(String, default="其他")
    verified_at = Column(String, default="")
    status = Column(String, default="待确认")
    link_status = Column(String, default='{"notice": "待确认", "registration": "待确认"}')
    review_note = Column(String, default="")
    # ---- V1.0 推荐专业（田淋元规则 2026-09-11）----
    recommended_majors = Column(String, default="[]")  # 10 枚举 JSON 数组；无依据为 []
    recommended_major_reason = Column(String, nullable=True, default=None)  # 30-150 字依据；无依据为 NULL
