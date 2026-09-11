"""CRUD 操作。"""
import json
from typing import List, Optional

from sqlalchemy.orm import Session

from . import models, schemas

# ORM 中以 JSON 字符串存储的字段 -> 解析失败/为空时的默认值
JSON_FIELDS = {
    "eligible_grades": [],
    "tags": [],
    "link_status": {"notice": "待确认", "registration": "待确认"},
    "recommended_majors": [],
}


def _to_out(c: models.Contest) -> schemas.ContestOut:
    data = {"id": c.id}
    for field in schemas.ContestOut.model_fields:
        if field == "id":
            continue
        raw = getattr(c, field, None)
        if field in JSON_FIELDS:
            try:
                data[field] = json.loads(raw) if raw else JSON_FIELDS[field]
            except (json.JSONDecodeError, TypeError):
                data[field] = JSON_FIELDS[field]
        elif raw is not None:
            data[field] = raw
        # raw 为 None 的字符串字段交给 schema 默认值
    return schemas.ContestOut(**data)


def _apply(obj: models.Contest, data: dict) -> None:
    for key, value in data.items():
        if value is None:
            continue
        if key in JSON_FIELDS:
            setattr(obj, key, json.dumps(value, ensure_ascii=False))
        else:
            setattr(obj, key, value)


def list_contests(
    db: Session,
    category: Optional[str] = None,
    status: Optional[str] = None,
    eligible_grades: Optional[str] = None,
    major: Optional[str] = None,
) -> List[schemas.ContestOut]:
    q = db.query(models.Contest)
    if category:
        q = q.filter(models.Contest.category == category)
    if status:
        q = q.filter(models.Contest.status == status)
    rows = q.all()
    result = [_to_out(r) for r in rows]
    if eligible_grades:
        result = [c for c in result if eligible_grades in c.eligible_grades]
    if major:
        # V1.0 规则：专业筛选只用于展示，不做硬删除——
        # 资格开放/命中/待确认，或推荐专业包含该专业，均保留；仅明确不符的隐藏
        from .recommend import major_eligibility

        def _visible(c):
            if major in (c.recommended_majors or []):
                return True
            return major_eligibility(c, major) in ("open", "match", "pending")

        result = [c for c in result if _visible(c)]
    return result


def get_contest(db: Session, contest_id: str) -> Optional[schemas.ContestOut]:
    row = db.query(models.Contest).filter(models.Contest.id == contest_id).first()
    return _to_out(row) if row else None


def create_contest(db: Session, payload: schemas.ContestCreate) -> schemas.ContestOut:
    import uuid

    contest_id = payload.id or f"c_{uuid.uuid4().hex[:12]}"
    obj = models.Contest(id=contest_id)
    data = payload.model_dump(exclude={"id"})
    _apply(obj, data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return _to_out(obj)


def update_contest(
    db: Session, contest_id: str, payload: schemas.ContestUpdate
) -> Optional[schemas.ContestOut]:
    row = db.query(models.Contest).filter(models.Contest.id == contest_id).first()
    if not row:
        return None
    _apply(row, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(row)
    return _to_out(row)


def delete_contest(db: Session, contest_id: str) -> bool:
    row = db.query(models.Contest).filter(models.Contest.id == contest_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
