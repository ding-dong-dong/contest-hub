"""推荐算法：硬过滤 + 软评分。

规则依据：田淋元《大学生竞赛信息平台 V1.0 产品交付文档》第五章「基础推荐规则」。

一、硬过滤（先判断能不能参加）：
  1. 状态为「已截止/取消」，或报名截止日期已过 → 不进入推荐（列表/历史仍可查看）
  2. 年级明确不在适用范围 → 排除；适用年级未知 → 保留并标记「资格待确认」
  3. 专业为硬性限制且用户不符合 → 排除；「不限」或仅建议方向 → 保留
  4. 限指定院校且学校明确不符 → 排除；用户未填学校 → 保留并提示补充
  5. 官方来源/链接无法核验 → 不作高可信，标记 verification_pending

二、软评分（满分 100，键名对齐前端 V1 契约 scores）：
  major_interest    专业与兴趣   30  专业命中 20 + 兴趣按命中比例 0–10
  grade_experience  年级与经验   25  年级适配 15 + 经验×建议难度匹配 10（资料未知中性 5）
  time              时间可行性   20  投入不高于可投入时间 20 / 高一档 10 / 高两档及以上 0；未知中性 10
  value             可验证价值   15  能力训练 5 + 成果产出 5 + 覆盖范围明确 5（均须有资料依据）
  trust             信息可信度   10  通知可访问 4 + 报名入口可访问 3 + 近 30 天核查 3

三、排序：总分降序；同分依次按「尚未截止 → 截止日期更近 → 核查日期更新」。
"""
import re
from datetime import date
from typing import List, Optional, Tuple

from . import schemas

# ---- 常量 ----
EXCLUDED_STATUS = {"已截止", "取消"}

# 用户每周可投入时间档位（索引即档位，越大时间越充裕）
TIME_BANDS = ["≤3小时", "4-7小时", "8-14小时", "≥15小时"]
TIME_BAND_INDEX = {name: i for i, name in enumerate(TIME_BANDS)}

# 竞赛预计投入档位名称（与用户时间档位对应）
EFFORT_BAND_NAMES = ["低（≤3小时/周）", "中（4-7小时/周）", "高（8-14小时/周）", "很高（≥15小时/周）"]

# 预计投入关键词 -> 档位（关键词优先于小时数解析）
_EFFORT_KEYWORD_BAND = (
    (("低", "轻松", "较少"), 0),
    (("中", "适度", "适中"), 1),
    (("高", "密集", "较多", "大量", "长"), 2),
)

# 参赛经验等级；建议难度等级：0 低 / 1 中 / 2 高
EXPERIENCE_LEVEL = {"无经验": 0, "参加过但未获奖": 1, "有获奖经验": 2}
DIFFICULTY_NAMES = ["低", "中", "高"]

# 兴趣关键词 -> 竞赛文本中可能出现的关联词
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

# 专业大类 -> 竞赛文本关联词（用于判断专业是否命中）
MAJOR_KEYWORDS = {
    "计算机": ["计算机", "软件", "程序", "编程", "算法", "人工智能", "AI", "数据", "互联网", "信息"],
    "电子信息": ["电子", "通信", "嵌入式", "单片机", "硬件", "EDA", "集成电路", "自动化"],
    "经管": ["经济", "管理", "商业", "创业", "市场", "财务", "金融", "营销", "电子商务"],
    "设计": ["设计", "视觉", "UI", "UX", "工业设计", "广告", "艺术", "传媒"],
    "机械": ["机械", "制造", "机器人", "工程制图", "机电"],
    "材料": ["材料", "化学", "化工", "高分子"],
    "理学": ["数学", "物理", "统计", "理学", "建模"],
    "文法": ["法学", "法律", "中文", "语言", "英语", "作文", "新闻", "传播", "新媒体", "社会工作"],
    "医学": ["医学", "药", "护理", "临床", "生物"],
    "其他": [],
}


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _effort_band(estimated_time: str) -> Optional[int]:
    """把竞赛预计投入文本解析为时间档位 0–3；无可靠依据返回 None（按中性处理）。"""
    if not estimated_time:
        return None
    for kws, band in _EFFORT_KEYWORD_BAND:
        if any(k in estimated_time for k in kws):
            return band
    nums = [int(x) for x in re.findall(r"\d+", estimated_time)]
    if nums:
        h = max(nums)
        if h <= 3:
            return 0
        if h <= 7:
            return 1
        if h <= 14:
            return 2
        return 3
    return None


def _difficulty_level(band: Optional[int]) -> Optional[int]:
    """投入档位 -> 建议难度：低/中/高（8 小时/周以上视为高）。"""
    if band is None:
        return None
    return 0 if band == 0 else 1 if band == 1 else 2


# ---------- 硬过滤 ----------
def _hard_filter(contest: schemas.ContestOut, user: schemas.UserProfile) -> Optional[str]:
    """返回 None 表示通过；返回字符串表示被剔除的原因。"""
    if contest.status in EXCLUDED_STATUS:
        return f"状态为「{contest.status}」，不进入推荐"
    deadline = _parse_date(contest.registration_deadline)
    if deadline and deadline < date.today():
        return f"报名已于 {deadline.isoformat()} 截止"
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
def _major_interest_score(
    contest: schemas.ContestOut, user: schemas.UserProfile
) -> Tuple[float, str, bool, List[str]]:
    """专业与兴趣 30：专业命中 20；兴趣按命中比例 0–10。"""
    text = " ".join(
        [contest.category, " ".join(contest.tags), contest.skills, contest.name, contest.major_limit]
    )
    major_hit = (
        contest.major_limit == "不限"
        or bool(user.major and user.major in contest.major_limit)
        or any(kw in text for kw in MAJOR_KEYWORDS.get(user.major, []))
    )
    major_part = 20.0 if major_hit else 0.0

    hits: List[str] = []
    if not user.interests:
        interest_part = 5.0  # 未提供兴趣按中性处理
        interest_note = "未提供兴趣，兴趣项按中性 5 分"
    else:
        for it in user.interests:
            kws = INTEREST_KEYWORDS.get(it, [it])
            if any(kw in text for kw in kws):
                hits.append(it)
        interest_part = round(10 * len(hits) / len(user.interests), 1)
        interest_note = f"兴趣命中：{'、'.join(hits)}" if hits else "兴趣标签未命中（0/10）"

    score = round(major_part + interest_part, 2)
    note = f"专业{'命中' if major_hit else '未命中'}（{major_part:g}/20）；{interest_note}（{interest_part:g}/10）"
    return score, note, major_hit, hits


def _grade_exp_score(
    contest: schemas.ContestOut, user: schemas.UserProfile
) -> Tuple[float, str, Optional[int]]:
    """年级与经验 25：年级适配 15；经验与建议难度匹配 10（资料未知中性 5）。"""
    if not contest.eligible_grades:
        grade_part = 10.0
        grade_note = "适用年级未知，年级项按中性 10 分并标记资格待确认"
    elif user.grade in contest.eligible_grades:
        grade_part = 15.0
        grade_note = f"年级{user.grade}在适用范围内（15/15）"
    else:
        grade_part = 5.0
        grade_note = "年级不在适用范围（5/15）"

    band = _effort_band(contest.estimated_time)
    diff = _difficulty_level(band)
    exp_lvl = EXPERIENCE_LEVEL.get(user.experience, 1)
    if diff is None:
        exp_part = 5.0
        exp_note = "竞赛建议难度/投入无可靠依据，经验匹配按中性 5 分"
    else:
        exp_part = float(max(0, 10 - 5 * abs(exp_lvl - diff)))
        exp_note = f"经验「{user.experience}」与建议难度「{DIFFICULTY_NAMES[diff]}」匹配（{exp_part:g}/10）"

    score = round(grade_part + exp_part, 2)
    return score, f"{grade_note}；{exp_note}", band


def _time_score(
    contest: schemas.ContestOut, user: schemas.UserProfile, band: Optional[int]
) -> Tuple[float, str]:
    """时间可行性 20：投入不高于可投入时间 20；高一档 10；高两档及以上 0；未知中性 10。"""
    u = TIME_BAND_INDEX.get(user.time_per_week)
    if u is None:
        return 10.0, "每周可投入时间档位未知，按中性 10 分处理"
    if band is None:
        return 10.0, "竞赛预计投入无可靠数据，按中性 10 分并提示"
    if band <= u:
        return 20.0, f"预计投入{EFFORT_BAND_NAMES[band]}，不高于你的可投入时间（{user.time_per_week}）"
    if band == u + 1:
        return 10.0, f"预计投入{EFFORT_BAND_NAMES[band]}，比你的可投入时间（{user.time_per_week}）高一档"
    return 0.0, f"预计投入{EFFORT_BAND_NAMES[band]}，比你的可投入时间（{user.time_per_week}）高两档及以上"


def _value_score(contest: schemas.ContestOut) -> Tuple[float, str]:
    """可验证价值 15：能力训练说明 5；成果产出说明 5；面向全国或覆盖范围明确 5。"""
    score = 0.0
    parts: List[str] = []
    if contest.skills and contest.skills.strip():
        score += 5.0
        parts.append("有能力训练说明（5）")
    if contest.outcomes and contest.outcomes.strip():
        score += 5.0
        parts.append("有成果产出说明（5）")
    if contest.school_limit and contest.school_limit != "待确认":
        score += 5.0
        parts.append(f"覆盖范围明确（{contest.school_limit}，5）")
    if not parts:
        parts.append("能力训练/成果产出/覆盖范围均缺少资料依据（0）")
    return score, "、".join(parts)


def _trust_score(contest: schemas.ContestOut) -> Tuple[float, str]:
    """信息可信度 10：官方通知可访问 4；官方报名入口可访问 3；近 30 天核查 3。"""
    score = 0.0
    parts: List[str] = []
    ls = contest.link_status
    if contest.notice_url and ls.notice == "可用":
        score += 4.0
        parts.append("官方通知可访问（4）")
    else:
        parts.append("官方通知" + ("待复核/失效（0）" if contest.notice_url else "缺失（0）"))
    if contest.registration_url and ls.registration == "可用":
        score += 3.0
        parts.append("官方报名入口可访问（3）")
    else:
        parts.append("官方报名入口" + ("待复核/失效（0）" if contest.registration_url else "缺失或未开放（0）"))
    v = _parse_date(contest.verified_at)
    if v:
        days = (date.today() - v).days
        if days <= 30:
            score += 3.0
            parts.append(f"{days}天内刚核查（3）")
        else:
            parts.append(f"核查已超过30天（{days}天，0）")
    else:
        parts.append("无核查时间记录（0）")
    return score, "、".join(parts)


# ---------- 告警与待确认标记 ----------
def _build_warnings(
    contest: schemas.ContestOut, user: schemas.UserProfile
) -> Tuple[List[str], bool, bool]:
    warnings: List[str] = []
    qualification_pending = False
    verification_pending = False

    if not contest.registration_deadline:
        warnings.append("报名截止日期待确认，请以官网通知为准")
    if contest.school_limit == "待确认" or not contest.eligible_grades:
        qualification_pending = True
        warnings.append("适用院校/年级范围待人工确认")
    if contest.school_limit and contest.school_limit not in {"全国", "待确认"} and not user.school:
        qualification_pending = True
        warnings.append("该竞赛限指定院校，建议补充学校信息以核对资格")
    if contest.status == "待确认":
        verification_pending = True
        warnings.append("竞赛当前状态待复核")
    ls = contest.link_status
    if not contest.notice_url or ls.notice != "可用":
        verification_pending = True
        warnings.append("官方通知链接" + ("待复核/失效" if contest.notice_url else "缺失"))
    if contest.registration_url:
        if ls.registration != "可用":
            verification_pending = True
            warnings.append("官方报名链接待复核/失效")
    else:
        verification_pending = True
        warnings.append("官方报名入口缺失或尚未开放，请以官方通知为准")
    if not contest.verified_at:
        verification_pending = True
    if not contest.estimated_time:
        warnings.append("预计投入暂无可靠数据，时间可行性按中性评估")
    return warnings, qualification_pending, verification_pending


def _match_level(total: float) -> str:
    """展示分层：80–100 高度匹配；60–79 较为匹配；0–59 可进一步了解。"""
    if total >= 80:
        return "高度匹配"
    if total >= 60:
        return "较为匹配"
    return "可进一步了解"


def _summary_reason(
    contest: schemas.ContestOut,
    user: schemas.UserProfile,
    major_hit: bool,
    interest_hits: List[str],
    band: Optional[int],
    time_s: float,
    has_pending: bool,
) -> str:
    """产品文档第五章第 5 节：推荐理由生成模板。"""
    facets: List[str] = []
    if major_hit:
        facets.append(f"专业「{user.major}」")
    if interest_hits:
        facets.append(f"兴趣「{'、'.join(interest_hits)}」")
    if contest.eligible_grades and user.grade in contest.eligible_grades:
        facets.append(f"年级「{user.grade}」")
    facets.append(f"经验「{user.experience}」")

    targets: List[str] = []
    if contest.category or contest.tags:
        tag_text = "、".join(x for x in [contest.category, *contest.tags] if x)
        if tag_text:
            targets.append(f"赛道（{tag_text}）")
    if contest.skills:
        targets.append("能力要求")
    if contest.major_limit or contest.eligible_grades:
        targets.append("参赛对象")

    if band is None:
        time_phrase = "竞赛预计每周投入时长暂无可靠数据，时间匹配按中性评估"
    elif time_s >= 20:
        time_phrase = (
            f"预计每周投入{contest.estimated_time}，在你的可投入时间（{user.time_per_week}）范围内"
        )
    else:
        time_phrase = (
            f"预计每周投入{contest.estimated_time}，可能超过你的可投入时间（{user.time_per_week}）"
        )

    msg = (
        f"推荐给你：{contest.name}。"
        f"你的{'、'.join(facets)}与该竞赛的{'、'.join(targets) or '参赛要求'}匹配；"
        f"{time_phrase}。"
        f"报名截止{contest.registration_deadline or '待确认'}，"
        f"信息最近核查于{contest.verified_at or '待确认'}。"
    )
    if has_pending:
        msg += "存在资格或资料待确认项，请注意下方风险提示。"
    msg += "请在报名前阅读官方通知确认最终资格。"
    return msg


def score_contest(contest: schemas.ContestOut, user: schemas.UserProfile) -> schemas.RecommendItem:
    s1, r1, major_hit, interest_hits = _major_interest_score(contest, user)
    s2, r2, band = _grade_exp_score(contest, user)
    s3, r3 = _time_score(contest, user, band)
    s4, r4 = _value_score(contest)
    s5, r5 = _trust_score(contest)

    total = round(s1 + s2 + s3 + s4 + s5, 2)
    warnings, qual_pending, ver_pending = _build_warnings(contest, user)
    summary = _summary_reason(
        contest, user, major_hit, interest_hits, band, s3, qual_pending or ver_pending
    )
    reasons = [
        summary,
        f"专业与兴趣 {s1}/30：{r1}",
        f"年级与经验 {s2}/25：{r2}",
        f"时间可行性 {s3}/20：{r3}",
        f"可验证价值 {s4}/15：{r4}",
        f"信息可信度 {s5}/10：{r5}",
    ]

    return schemas.RecommendItem(
        competition_id=contest.id,
        total_score=total,
        match_level=_match_level(total),
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


def _sort_key(pair: Tuple[schemas.ContestOut, schemas.RecommendItem]):
    """同分排序：尚未截止优先 → 截止日期更近优先 → 核查日期更新优先。"""
    contest, item = pair
    today = date.today()
    deadline = _parse_date(contest.registration_deadline)
    verified = _parse_date(contest.verified_at)
    open_rank = 0 if (deadline and deadline >= today) else 1   # 截止日期明确且未过的排前
    deadline_key = deadline.toordinal() if deadline else 999999  # 日期更近（ordinal 更小）排前
    verified_key = -verified.toordinal() if verified else 0     # 更新（ordinal 更大 → 负值更小）排前
    return (-item.total_score, open_rank, deadline_key, verified_key)


def recommend(
    contests: List[schemas.ContestOut], user: schemas.UserProfile
) -> List[schemas.RecommendItem]:
    scored: List[Tuple[schemas.ContestOut, schemas.RecommendItem]] = []
    for c in contests:
        if _hard_filter(c, user):
            continue
        scored.append((c, score_contest(c, user)))
    scored.sort(key=_sort_key)
    return [item for _, item in scored]
