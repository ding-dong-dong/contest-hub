"""2 条示例竞赛数据，仅在表为空时写入。"""
import json

from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal

SAMPLE_CONTESTS = [
    {
        "id": "c_001_ai_challenge",
        "name": "2026 全国大学生人工智能创新挑战赛（第八届）",
        "category": "AI/算法",
        "organizer": "教育部高等学校计算机类专业教学指导委员会",
        "eligible_grades": ["大二", "大三", "大四", "研究生"],
        "major_limit": "计算机,电子信息,理学",
        "school_limit": "全国",
        "registration_deadline": "2026-10-15",
        "submission_deadline": "2026-11-30",
        "materials": "报名表+作品报告+源码仓库+演示视频",
        "skills": "机器学习、深度学习、数据分析、论文撰写",
        "estimated_time": "高投入（每周 10 小时以上）",
        "notice_url": "https://example.edu.cn/aic2026/notice",
        "registration_url": "https://example.edu.cn/aic2026/register",
        "source_type": "官网",
        "verified_at": "2026-09-05",
        "status": "报名中",
        "review_note": "认可度高，建议大三以上同学组队",
    },
    {
        "id": "c_002_biz_plan",
        "name": "2026「创青春」全国大学生创业计划大赛",
        "category": "创新创业/商业分析",
        "organizer": "共青团中央 / 全国学联",
        "eligible_grades": ["大一", "大二", "大三", "大四", "研究生"],
        "major_limit": "不限",
        "school_limit": "全国",
        "registration_deadline": "2026-09-30",
        "submission_deadline": "2026-11-10",
        "materials": "商业计划书+路演PPT+团队信息表",
        "skills": "市场调研、商业模式设计、财务测算、路演表达",
        "estimated_time": "中等投入（每周 5-8 小时）",
        "notice_url": "https://example.org/cy2026",
        "registration_url": "",
        "source_type": "官方公众号",
        "verified_at": "2026-09-01",
        "status": "即将截止",
        "review_note": "适合跨学科组队，文法/经管同学优先",
    },
]


def seed_if_empty() -> None:
    db: Session = SessionLocal()
    try:
        if db.query(models.Contest).count() > 0:
            return
        for item in SAMPLE_CONTESTS:
            data = dict(item)
            grades = data.pop("eligible_grades")
            db.add(
                models.Contest(
                    **data,
                    eligible_grades=json.dumps(grades, ensure_ascii=False),
                )
            )
        db.commit()
    finally:
        db.close()
