"""CRUD 操作。"""
import json
from typing import List, Optional

from sqlalchemy.orm import Session

from . import models, schemas


def _to_out(c: models.Contest) -> schemas.ContestOut:
    return schemas.ContestOut(
        id=c.id,
        name=c.name,
        category=c.category or "",
        organizer=c.organizer or "",
        eligible_grades=json.loads(c.eligible_grades or "[]"),
        major_limit=c.major_limit or "不限",
        school_limit=c.school_limit or "待确认",
        registration_deadline=c.registration_deadline or "",
        submission_deadline=c.submission_deadline or "",
        materials=c.materials or "",
        skills=c.skills or "",
        estimated_time=c.estimated_time or "",
        notice_url=c.notice_url or "",
        registration_url=c.registration_url or "",
        source_type=c.source_type or "其他",
        verified_at=c.verified_at or "",
        status=c.status or "待确认",
        review_note=c.review_note or "",
    )


def _apply(obj: models.Contest, data: dict) -> None:
    for key, value in data.items():
        if value is None:
            continue
        if key == "eligible_grades":
            setattr(obj, key, json.dumps(value, ensure_ascii=False))
        else:
            setattr(obj, key, value)


def list_contests(
    db: Session,
    category: Optional[str] = None,
    status: Optional[str] = None,
    eligible_grades: Optional[str] = None,
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
