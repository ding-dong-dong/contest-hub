"""推荐算法：硬过滤 + 软评分。

软评分维度（满分 100）：
  专业兴趣   30
  年级经验   25
  时间可行性 20
  可验证价值 15
  信息可信度 10
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


# ---------- 软评分 ----------
def _interest_score(contest: schemas.ContestOut, interests: List[str]) -> Tuple[float, str]:
    if not interests:
        return 10.0, "未提供兴趣，给基础分"
    text = " ".join([contest.category, contest.skills, contest.materials, contest.name])
    hits = []
    for it in interests:
        kws = INTEREST_KEYWORDS.get(it, [it])
        if any(kw in text for kw in kws):
            hits.append(it)
    score = round(30 * (len(hits) / len(interests)), 2)
    if hits:
        return score, f"兴趣命中 {hits}"
    return 5.0, "兴趣未直接命中"


def _grade_exp_score(contest: schemas.ContestOut, user: schemas.UserProfile) -> Tuple[float, str]:
    grade_ok = (not contest.eligible_grades) or (user.grade in contest.eligible_grades)
    exp_w = EXPERIENCE_WEIGHT.get(user.experience, 0.5)
    base = 15.0 if grade_ok else 5.0
    score = round(base + 10 * exp_w, 2)
    parts = []
    if grade_ok:
        parts.append("年级匹配")
    parts.append(f"经验权重 {exp_w}")
    return min(score, 25.0), "；".join(parts)


def _time_score(contest: schemas.ContestOut, user: schemas.UserProfile) -> Tuple[float, str]:
    band = TIME_BAND.get(user.time_per_week)
    if band is None:
        return 8.0, "时间档未知"
    # 没有标注预计投入时按中位档给基础分
    if not contest.estimated_time:
        if band[0] >= 8:
            return 18.0, "时间充足（无投入标注，默认可承担）"
        if band[0] >= 4:
            return 12.0, "时间适中"
        return 6.0, "时间可能不足"
    et = contest.estimated_time
    if any(k in et for k in ["低", "轻松", "短"]) and band[0] <= 3:
        return 18.0, "投入低且你时间较少，匹配"
    if any(k in et for k in ["高", "大", "长", "密集"]) and band[0] >= 8:
        return 20.0, "投入高且你时间充足，匹配"
    if band[0] >= 8:
        return 16.0, "时间充足"
    if band[0] >= 4:
        return 12.0, "时间适中"
    return 8.0, "时间偏紧"


def _verifiable_score(contest: schemas.ContestOut) -> Tuple[float, str]:
    score = 0.0
    if contest.notice_url:
        score += 8.0
    if contest.registration_url:
        score += 7.0
    return score, f"通知链接{'+8' if contest.notice_url else ''}{' +报名链接+7' if contest.registration_url else ''}"


def _trust_score(contest: schemas.ContestOut) -> Tuple[float, str]:
    src_w = SOURCE_TRUST.get(contest.source_type, 0.5)
    base = round(10 * src_w, 2)
    # 核查时间近度
    v = _parse_date(contest.verified_at)
    recency = ""
    if v:
        days = (date.today() - v).days
        if days <= 14:
            recency = "，近期核查"
        elif days <= 60:
            recency = "，核查适中"
        else:
            recency = "，核查较久"
    return base, f"来源{contest.source_type}({src_w}){recency}"


def score_contest(contest: schemas.ContestOut, user: schemas.UserProfile) -> Tuple[float, str]:
    """返回 (总分, 汇总理由)。"""
    s1, r1 = _interest_score(contest, user.interests)
    s2, r2 = _grade_exp_score(contest, user)
    s3, r3 = _time_score(contest, user)
    s4, r4 = _verifiable_score(contest)
    s5, r5 = _trust_score(contest)
    total = round(s1 + s2 + s3 + s4 + s5, 2)
    reason = (
        f"专业兴趣{s1}/30（{r1}）；"
        f"年级经验{s2}/25（{r2}）；"
        f"时间可行性{s3}/20（{r3}）；"
        f"可验证价值{s4}/15（{r4}）；"
        f"信息可信度{s5}/10（{r5}）"
    )
    return total, reason


def recommend(
    contests: List[schemas.ContestOut], user: schemas.UserProfile
) -> List[schemas.RecommendItem]:
    scored: List[schemas.RecommendItem] = []
    for c in contests:
        reason = _hard_filter(c, user)
        if reason:
            continue
        total, why = score_contest(c, user)
        scored.append(
            schemas.RecommendItem(contest=c, score=total, reason=why)
        )
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored
