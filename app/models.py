"""SQLAlchemy ORM ????

??ζ??????????????? + ??????V1 ?????????????????
??session/tags/process/outcomes/link_status????
list/dict ????? JSON ?????????洢??
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
    major_limit = Column(String, default="????")
    school_limit = Column(String, default="?????")
    registration_deadline = Column(String, default="")
    submission_deadline = Column(String, default="")
    materials = Column(String, default="")
    process = Column(String, default="")
    skills = Column(String, default="")
    outcomes = Column(String, default="")
    ability_training = Column(String, default="")
    estimated_time = Column(String, default="")
    notice_url = Column(String, default="")
    registration_url = Column(String, default="")
    source_type = Column(String, default="????")
    verified_at = Column(String, default="")
    status = Column(String, default="?????")
    link_status = Column(String, default='{"notice": "?????", "registration": "?????"}')
    review_note = Column(String, default="")
