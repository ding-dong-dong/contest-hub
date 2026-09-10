"""Pydantic 请求/响应模型。

对外字段统一使用 snake_case；前端 adapter 负责映射为页面驼峰字段
（见连诗钰《V1 字段映射与交接》）。
"""
from typing import List, Optional

from pydantic import BaseModel, Field

# 链接复核状态：可用 / 失效 / 待确认（未提供时前端按「待确认」处理）
LINK_STATUS_VALUES = ("可用", "失效", "待确认")


class LinkStatus(BaseModel):
    notice: str = "待确认"        # 官方通知链接复核状态
    registration: str = "待确认"  # 官方报名链接复核状态


class ContestBase(BaseModel):
    name: str
    # ---- 前端 V1 契约新增字段 ----
    session: str = ""                  # 本届届次
    tags: List[str] = Field(default_factory=list)  # 竞赛标签（可多个）
    category: str = ""
    organizer: str = ""
    eligible_grades: List[str] = Field(default_factory=list)
    major_limit: str = "不限"
    school_limit: str = "待确认"
    registration_deadline: str = ""
    submission_deadline: Optional[str] = ""
    materials: str = ""
    process: str = ""                  # 提交流程
    skills: str = ""
    outcomes: str = ""                 # 能力/成果产出
    estimated_time: Optional[str] = ""
    notice_url: str = ""
    registration_url: Optional[str] = ""
    source_type: str = "其他"
    verified_at: str = ""
    status: str = "待确认"
    link_status: LinkStatus = Field(default_factory=LinkStatus)
    review_note: Optional[str] = ""


class ContestCreate(ContestBase):
    # 可选，未提供时由系统生成
    id: Optional[str] = None


class ContestUpdate(BaseModel):
    name: Optional[str] = None
    session: Optional[str] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    organizer: Optional[str] = None
    eligible_grades: Optional[List[str]] = None
    major_limit: Optional[str] = None
    school_limit: Optional[str] = None
    registration_deadline: Optional[str] = None
    submission_deadline: Optional[str] = None
    materials: Optional[str] = None
    process: Optional[str] = None
    skills: Optional[str] = None
    outcomes: Optional[str] = None
    estimated_time: Optional[str] = None
    notice_url: Optional[str] = None
    registration_url: Optional[str] = None
    source_type: Optional[str] = None
    verified_at: Optional[str] = None
    status: Optional[str] = None
    link_status: Optional[LinkStatus] = None
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


class ScoreBreakdown(BaseModel):
    """推荐评分明细（满分 100），与前端契约键名一致。"""
    major_interest: float = 0.0    # 专业兴趣 30
    grade_experience: float = 0.0  # 年级经验 25
    time: float = 0.0              # 时间可行性 20
    value: float = 0.0             # 可验证价值 15
    trust: float = 0.0             # 信息可信度 10


class RecommendItem(BaseModel):
    """前端 V1 契约：扁平字段 + 分数明细 + 理由/告警/待确认标记。"""
    competition_id: str = Field(description="竞赛 ID，对应 contest.id")
    total_score: float = Field(description="推荐总分（0-100），等于 scores 五项之和")
    match_level: str = Field(
        default="",
        description="匹配档位标签（产品文档第五章第4节）：高度匹配(80-100)/较为匹配(60-79)/可进一步了解(0-59)",
    )
    scores: ScoreBreakdown
    reasons: List[str] = Field(
        default_factory=list, description="个性化推荐理由，第1条为总结（含免责声明），至少2条"
    )
    warnings: List[str] = Field(default_factory=list, description="风险提示文案，如截止日期待确认、链接待复核")
    qualification_pending: bool = Field(
        default=False, description="资格范围待人工确认（适用年级/院校不明），true 时前端必须显示风险提示"
    )
    verification_pending: bool = Field(
        default=False, description="链接/状态待复核，true 时对应官方入口需标注待确认"
    )
    # 附带完整竞赛对象，前端可直接渲染，无需再按 id 关联
    contest: ContestOut


class RecommendResponse(BaseModel):
    total: int
    items: List[RecommendItem]
