"""Pydantic 请求/响应模型。"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ContestBase(BaseModel):
    name: str
    category: str = ""
    organizer: str = ""
    eligible_grades: List[str] = Field(default_factory=list)
    major_limit: str = "不限"
    school_limit: str = "待确认"
    registration_deadline: str = ""
    submission_deadline: Optional[str] = ""
    materials: str = ""
    skills: str = ""
    estimated_time: Optional[str] = ""
    notice_url: str = ""
    registration_url: Optional[str] = ""
    source_type: str = "其他"
    verified_at: str = ""
    status: str = "待确认"
    review_note: Optional[str] = ""


class ContestCreate(ContestBase):
    # 可选，未提供时由系统生成
    id: Optional[str] = None


class ContestUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    organizer: Optional[str] = None
    eligible_grades: Optional[List[str]] = None
    major_limit: Optional[str] = None
    school_limit: Optional[str] = None
    registration_deadline: Optional[str] = None
    submission_deadline: Optional[str] = None
    materials: Optional[str] = None
    skills: Optional[str] = None
    estimated_time: Optional[str] = None
    notice_url: Optional[str] = None
    registration_url: Optional[str] = None
    source_type: Optional[str] = None
    verified_at: Optional[str] = None
    status: Optional[str] = None
    review_note: Optional[str] = None


class ContestOut(ContestBase):
    id: str

    class Config:
        from_attributes = True


# ---- 推荐接口 ----
class UserProfile(BaseModel):
    grade: str  # 大一/大二/大三/大四/研究生/其他
    major: str  # 计算机/电子信息/经管/设计/机械/材料/理学/文法/医学/其他
    interests: List[str] = Field(default_factory=list)
    experience: str  # 无经验/参加过但未获奖/有获奖经验
    time_per_week: str  # ≤3小时/4-7小时/8-14小时/≥15小时
    school: Optional[str] = ""


class RecommendItem(BaseModel):
    contest: ContestOut
    score: float
    reason: str


class RecommendResponse(BaseModel):
    total: int
    items: List[RecommendItem]
