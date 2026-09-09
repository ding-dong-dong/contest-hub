"""推荐算法：硬过滤 + 软评分。

软评分维度（满分 100，键名对齐前端 V1 契约 scores）：
  major_interest    专业兴趣   30
  grade_experience  年级经验   25
  time              时间可行性 20
  value             可验证价值 15
  trust             信息可信度 10
"""
from datetime import date
from typing import List, Tuple

from . import schemas

# ---- 常量 ----
EXCLUDED_STATUS = {"已截止", "取消"}

# 时间档位 -> 估算可投入小时区间
TIME_BAND = {
    "≤3小时": (0, 3),
    "4-7小时": (4, 7),
    "8-14小时": (8, 14),
    "≥15小时": (15, 999),
}

SOURCE_TRUST = {"官网": 1.0, "官方公众号": 0.8, "其他": 0.5}

# 兴趣关键词 -> 关联竞赛类别/技能关键词
INTEREST_KEYWORDS = {
    "AI": ["AI", "人工智能", "机器学习", "深度学习", "算法"],
    "编程": ["编程", "程序设计", "ACM", "代码", "软件开发"],
    "创新创业": ["创业", "创新", "互联网+", "商业计划"],
    "商业分析": ["商业", "经管", "市场", "财务", "案例分析"],
    "设计": ["设计", "视觉", "UI", "UX", "工业设计"],
    "数学建模": ["数学", "建模", "数模"],
    "电子": ["电子", "嵌入式", "单片机", "硬件", "EDA"],
    "公益": ["公益", "志愿", "社会服务"],
}

EXPERIENCE_WEIGHT = {
    "无经验": 0.4,
    "参加过但未获奖": 0.7,
    "有获奖经验": 1.0,
}


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# ---------- 硬过滤 ----------
def _hard_filter(contest: schemas.ContestOut, user: schemas.UserProfile) -> str | None:
    """返回 None 表示通过；返回字符串表示被剔除的原因。"""
    if contest.status in EXCLUDED_STATUS:
        return f"状态为「{contest.status}」，不推荐"
    if contest.eligible_grades and user.grade not in contest.eligible_grades:
        return f"年级不匹配（要求 {contest.eligible_grades}）"
    if contest.major_limit and contest.major_limit != "不限":
        if user.major not in contest.major_limit:
            return f"专业受限于「{contest.major_limit}」"
    if contest.school_limit and contest.school_limit not in {"全国", "待确认"}:
        if user.school and user.school not in contest.school_limit:
            return f"院校受限于「{contest.school_limit}」"
    return None


# ---------- 软评分（每个维度返回 分数 + 简短理由）----------
def _interest_score(contest: schemas.ContestOut, interests: List[str]) -> Tuple[float, str]:
    if not interests:
        return 10.0, "未提供兴趣，按基础分处理"
    text = " ".join([contest.category, " ".join(contest.tags), contest.skills, contest.materials, contest.name])
    hits = []
    for it in interests:
        kws = INTEREST_KEYWORDS.get(it, [it])
        if any(kw in text for kw in kws):
            hits.append(it)
    score = round(30 * (len(hits) / len(interests)), 2)
    if hits:
        return score, f"兴趣命中：{ '、'.join(hits) }"
    return 5.0, "兴趣与竞赛标签未直接匹配"


def _grade_exp_score(contest: schemas.ContestOut, user: schemas.UserProfile) -> Tuple[float, str]:
    grade_ok = (not contest.eligible_grades) or (user.grade in contest.eligible_grades)
    exp_w = EXPERIENCE_WEIGHT.get(user.experience, 0.5)
    base = 15.0 if grade_ok else 5.0
    score = round(min(base + 10 * exp_w, 25.0), 2)
    if grade_ok:
        return score, f"年级{user.grade}在适用范围内，经验「{user.experience}」"
    return score, f"年级匹配度低，经验「{user.experience}」"


def _time_score(contest: schemas.ContestOut, user: schemas.UserProfile) -> Tuple[float, str]:
    band = TIME_BAND.get(user.time_per_week)
    if band is None:
        return 8.0, "时间档位未知，按基础分处理"
    et = contest.estimated_time or ""
    if not et:
        if band[0] >= 8:
            return 18.0, "你每周时间充足，竞赛未标注高投入，默认可承担"
        if band[0] >= 4:
            return 12.0, "你每周时间适中"
        return 6.0, "你每周时间偏少，投入未标注需谨慎"
    if any(k in et for k in ["低", "轻松", "短"]) and band[0] <= 3:
        return 18.0, "竞赛投入低，与你较少的可投入时间匹配"
    if any(k in et for k in ["高", "大", "长", "密集"]) and band[0] >= 8:
        return 20.0, "竞赛投入高，你每周时间充足可承担"
    if band[0] >= 8:
        return 16.0, "你每周时间充足"
    if band[0] >= 4:
        return 12.0, "你每周时间适中"
    return 8.0, "你每周时间偏紧"


def _value_score(contest: schemas.ContestOut) -> Tuple[float, str]:
    score = 0.0
    parts = []
    if contest.notice_url:
        score += 8.0
        parts.append("有官方通知链接")
    if contest.registration_url:
        score += 7.0
        parts.append("有官方报名链接")
    if not parts:
        parts.append("缺少官方链接")
    return score, "、".join(parts)


def _trust_score(contest: schemas.ContestOut) -> Tuple[float, str]:
    src_w = SOURCE_TRUST.get(contest.source_type, 0.5)
    score = round(10 * src_w, 2)
    v = _parse_date(contest.verified_at)
    if v:
        days = (date.today() - v).days
        if days <= 14:
            return score, f"来源「{contest.source_type}」，{days}天内刚核查"
        if days <= 60:
            return score, f"来源「{contest.source_type}」，核查时间适中"
        return score, f"来源「{contest.source_type}」，核查时间较久（{days}天）"
    return score, f"来源「{contest.source_type}」，无核查时间记录"


# ---------- 告警与待确认标记 ----------
def _build_warnings(contest: schemas.ContestOut) -> Tuple[List[str], bool, bool]:
    warnings: List[str] = []
    qualification_pending = False
    verification_pending = False

    if not contest.registration_deadline:
        warnings.append("报名截止日期待确认，请以官网通知为准")
    if contest.school_limit == "待确认" or not contest.eligible_grades:
        qualification_pending = True
        warnings.append("适用院校/年级范围待人工确认")
    if contest.status == "待确认":
        verification_pending = True
        warnings.append("竞赛当前状态待复核")
    ls = contest.link_status
    if not contest.notice_url or ls.notice != "可用":
        verification_pending = True
        warnings.append("官方通知链接" + ("待复核" if contest.notice_url else "缺失"))
    if contest.registration_url and ls.registration != "可用":
        verification_pending = True
        warnings.append("官方报名链接待复核")
    if not contest.verified_at:
        verification_pending = True
    return warnings, qualification_pending, verification_pending


def score_contest(contest: schemas.ContestOut, user: schemas.UserProfile) -> schemas.RecommendItem:
    s1, r1 = _interest_score(contest, user.interests)
    s2, r2 = _grade_exp_score(contest, user)
    s3, r3 = _time_score(contest, user)
    s4, r4 = _value_score(contest)
    s5, r5 = _trust_score(contest)

    total = round(s1 + s2 + s3 + s4 + s5, 2)
    reasons = [
        f"专业兴趣 {s1}/30：{r1}",
        f"年级经验 {s2}/25：{r2}",
        f"时间可行性 {s3}/20：{r3}",
        f"可验证价值 {s4}/15：{r4}",
        f"信息可信度 {s5}/10：{r5}",
    ]
    warnings, qual_pending, ver_pending = _build_warnings(contest)

    return schemas.RecommendItem(
        competition_id=contest.id,
        total_score=total,
        scores=schemas.ScoreBreakdown(
            major_interest=s1,
            grade_experience=s2,
            time=s3,
            value=s4,
            trust=s5,
        ),
        reasons=reasons,
        warnings=warnings,
        qualification_pending=qual_pending,
        verification_pending=ver_pending,
        contest=contest,
    )


def recommend(
    contests: List[schemas.ContestOut], user: schemas.UserProfile
) -> List[schemas.RecommendItem]:
    scored: List[schemas.RecommendItem] = []
    for c in contests:
        if _hard_filter(c, user):
            continue
        scored.append(score_contest(c, user))
    scored.sort(key=lambda x: x.total_score, reverse=True)
    return scored
