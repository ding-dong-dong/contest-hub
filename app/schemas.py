"""Pydantic 请求/响应模型。

对外字段统一使用 snake_case；前端 adapter 负责映射为页面驼峰字段
（见连诗钰《V1 字段映射与交接》）。
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# 链接复核状态：可用 / 失效 / 待确认（未提供时前端按「待确认」处理）
LINK_STATUS_VALUES = ("可用", "失效", "待确认")

# 来源类型：对外只输出这 4 个标准中文值（前端 V1 契约；openapi 以 enum 暴露）
SOURCE_TYPE_VALUES = ("官网", "百度百科", "转载", "其他")
_SOURCE_TYPE_ALIASES = {
    "官网": "官网", "官方": "官网", "official": "官网", "website": "官网",
    "百度百科": "百度百科", "百科": "百度百科", "baidu_baike": "百度百科",
    "baike": "百度百科", "baidubaike": "百度百科",
    "转载": "转载", "转发": "转载", "repost": "转载", "reposted": "转载", "forward": "转载",
    "其他": "其他", "其它": "其他", "other": "其他", "others": "其他", "unknown": "其他",
}


def normalize_source_type(value) -> str:
    """把历史英文值/近义写法归一为 4 个标准中文枚举；无法识别时安全降级为「其他」。"""
    if value is None:
        return "其他"
    key = str(value).strip()
    return _SOURCE_TYPE_ALIASES.get(key, _SOURCE_TYPE_ALIASES.get(key.lower(), "其他"))


# 推荐专业枚举（田淋元《推荐专业规则与验收清单 V1.0》第 2 节，禁止其他表述）
RECOMMENDED_MAJOR_VALUES = (
    "计算机", "电子信息", "经管", "设计", "机械",
    "材料", "理学", "文法", "医学", "其他",
)
# 常见近义/英文写法 -> 统一枚举（入参宽容，出参严格）
_RECOMMENDED_MAJOR_ALIASES = {
    "计算机": "计算机", "软件": "计算机", "软件工程": "计算机", "cs": "计算机",
    "电子信息": "电子信息", "电子": "电子信息", "通信": "电子信息", "通信工程": "电子信息",
    "经管": "经管", "经济": "经管", "管理": "经管", "工商管理": "经管", "金融": "经管",
    "设计": "设计", "艺术设计": "设计", "数字媒体": "设计", "数媒": "设计",
    "机械": "机械", "机电": "机械", "机械工程": "机械",
    "材料": "材料", "材料科学": "材料", "高分子": "材料",
    "理学": "理学", "数学": "理学", "物理": "理学", "化学": "理学", "生物": "理学", "统计": "理学",
    "文法": "文法", "中文": "文法", "外语": "文法", "英语": "文法", "新闻": "文法",
    "传播": "文法", "新媒体": "文法", "法学": "文法", "法律": "文法",
    "医学": "医学", "临床": "医学", "护理": "医学", "药学": "医学", "医": "医学",
    "其他": "其他", "其它": "其他",
}
_MAJOR_SPLIT_RE_CHARS = "、,，;；/|"


def normalize_recommended_majors(value) -> list:
    """归一为枚举数组：接受 list 或「计算机、设计」/json 字符串；非法项剔除，未知安全忽略。

    「待确认」/空 -> []（规则：空推荐专业不报错，标记待确认）。
    """
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if not s or s in ("待确认", "无", "暂无", "[]", "null"):
            return []
        if s.startswith("["):
            try:
                import json
                value = json.loads(s)
            except ValueError:
                value = [s]
        else:
            for ch in _MAJOR_SPLIT_RE_CHARS:
                s = s.replace(ch, "、")
            value = [x for x in s.split("、")]
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        key = str(item).strip()
        if not key or key == "待确认":
            continue
        norm = key if key in RECOMMENDED_MAJOR_VALUES else _RECOMMENDED_MAJOR_ALIASES.get(
            key, _RECOMMENDED_MAJOR_ALIASES.get(key.lower())
        )
        if norm and norm not in out:
            out.append(norm)
    return out


def normalize_recommended_major_reason(value):
    """30-150 字依据；「待确认」/空 -> None（旧数据无此字段时接口返回 null，不报错）。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("待确认", "无", "暂无", "null", "None"):
        return None
    return s


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
    major_limit: str = "不限"  # 官方限制原文（不限专业/待确认/原文摘录），禁止改写成推荐专业
    recommended_majors: List[Literal["计算机", "电子信息", "经管", "设计", "机械",
                                     "材料", "理学", "文法", "医学", "其他"]] = Field(
        default_factory=list, description="推荐专业枚举数组；无依据返回 []"
    )
    recommended_major_reason: Optional[str] = Field(
        default=None, max_length=150,
        description="推荐依据（30-150字，基于赛道/任务/材料/评审标准）；无依据返回 null",
    )
    school_limit: str = "待确认"
    registration_deadline: Optional[str] = ""  # ISO 8601, null=未知
    registration_deadline_note: str = ""  # 补充说明（校内截止/赛道差异等）
    submission_deadline: Optional[str] = ""
    submission_deadline_note: str = ""
    materials: str = ""
    process: str = ""                  # 提交流程
    skills: str = ""
    outcomes: str = ""                 # 能力/成果产出
    ability_training: str = ""         # 能力训练说明（详细描述）
    estimated_time: Optional[str] = ""
    notice_url: str = ""
    registration_url: Optional[str] = ""
    source_type: Literal["官网", "百度百科", "转载", "其他"] = "其他"

    @field_validator("source_type", mode="before")
    @classmethod
    def _normalize_source_type(cls, value):
        # 归一化历史英文值（official/baidu_baike/repost）与近义写法为中文契约值
        return None if value is None else normalize_source_type(value)

    @field_validator("recommended_majors", mode="before")
    @classmethod
    def _normalize_recommended_majors(cls, value):
        return normalize_recommended_majors(value)

    @field_validator("recommended_major_reason", mode="before")
    @classmethod
    def _normalize_recommended_major_reason(cls, value):
        return normalize_recommended_major_reason(value)

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
    registration_deadline_note: Optional[str] = None
    submission_deadline: Optional[str] = None
    submission_deadline_note: Optional[str] = None
    materials: Optional[str] = None
    process: Optional[str] = None
    skills: Optional[str] = None
    outcomes: Optional[str] = None
    ability_training: Optional[str] = None
    estimated_time: Optional[str] = None
    notice_url: Optional[str] = None
    registration_url: Optional[str] = None
    source_type: Optional[Literal["官网", "百度百科", "转载", "其他"]] = None
    recommended_majors: Optional[List[Literal["计算机", "电子信息", "经管", "设计", "机械",
                                              "材料", "理学", "文法", "医学", "其他"]]] = None
    recommended_major_reason: Optional[str] = Field(default=None, max_length=150)
    verified_at: Optional[str] = None
    status: Optional[str] = None
    link_status: Optional[LinkStatus] = None
    review_note: Optional[str] = None

    @field_validator("source_type", mode="before")
    @classmethod
    def _normalize_source_type(cls, value):
        return None if value is None else normalize_source_type(value)

    @field_validator("recommended_majors", mode="before")
    @classmethod
    def _normalize_recommended_majors(cls, value):
        return None if value is None else normalize_recommended_majors(value)

    @field_validator("recommended_major_reason", mode="before")
    @classmethod
    def _normalize_recommended_major_reason(cls, value):
        return None if value is None else normalize_recommended_major_reason(value)


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
