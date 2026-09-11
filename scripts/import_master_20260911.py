#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导入《竞赛信息总表_20260911_已补全》到 contests.db（可重复执行的同步脚本）。

数据依据：田淋元 2026-09-11 复核的全量快照（数据来源：团队 Render API）。
处理规则（按陈玉婷 2026-09-11 指示）：
- data_review_status = 需补充 → 整条删除（不保留）
- data_review_status = 可录入 / 已录入 → 全字段 upsert（Excel 为权威快照）
- 待审核 → 跳过并告警

字段归一（防乱码/防脏数据）：
- tags / eligible_grades：顿号文本 -> JSON 数组；年级解析为标准枚举
  （大一/大二/大三/大四/研究生/其他），无法解析 -> []（资格待确认，不误杀）
- registration/submission_deadline：datetime 或文本 -> ISO8601+08:00（24:00 -> 次日 00:00）
- status：枚举外值（如「待下届通知」）-> 「待确认」
- notice_status / registration_status：契约外值 -> 「待确认」（不虚构链接可用性）
- recommended_majors -> 10 枚举数组；recommended_major_reason 30-150 字截断
- review_note = Excel「现有复核备注」+「复核结论说明」合并

用法：
    python scripts/import_master_20260911.py [xlsx路径]
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.schemas import normalize_recommended_majors, normalize_recommended_major_reason  # noqa: E402

DEFAULT_XLSX = (
    r"C:\Users\Lenovo\Documents\xwechat_files\wxid_xiyy9d1l0ic222_0726"
    r"\msg\file\2026-09\竞赛信息总表_20260911_已补全(1)(1).xlsx"
)
DB = os.path.join(ROOT, "contests.db")
REPORT = os.path.join(ROOT, "scripts", "_import_master_report.txt")

SHEET = "竞赛总表"
HEADER_ROW = 8  # 第 8 行为字段名，第 9 行起为数据

VALID_STATUS = {"报名中", "即将截止", "已截止", "待确认"}
LINK_CONTRACT = {"可用", "失效"}

# DB 中需要由 Excel 写入的全部字段（id 之外的列按 Excel 同名表头映射）
FIELDS = [
    "name", "session", "category", "tags", "organizer", "eligible_grades",
    "major_limit", "recommended_majors", "recommended_major_reason",
    "school_limit", "registration_deadline", "registration_deadline_note",
    "submission_deadline", "submission_deadline_note", "materials", "process",
    "skills", "outcomes", "ability_training", "estimated_time", "notice_url",
    "registration_url", "source_type", "verified_at", "status", "link_status",
    "review_note",
]


def parse_grades(text) -> list:
    """资格原文 -> 标准年级枚举数组；无法解析 -> []（视为待确认，不硬排除）。"""
    s = str(text or "")
    s2 = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)  # 去掉标点/空白，处理「本（专）科」等写法
    out: list = []
    for t in ("大一", "大二", "大三", "大四", "研究生"):
        if t in s2 and t not in out:
            out.append(t)
    if "三年级" in s2 and "大三" not in out:
        out.append("大三")
    if "四年级" in s2 and "大四" not in out:
        out.append("大四")
    if re.search(r"本.{0,2}科", s2):
        for t in ("大一", "大二", "大三", "大四"):
            if t not in out:
                out.append(t)
    if ("硕" in s2 or "博" in s2) and "研究生" not in out:
        out.append("研究生")
    if ("专科" in s2 or "高职" in s2 or "中专" in s2 or "社会人士" in s2) and "其他" not in out:
        out.append("其他")
    # 未点明本科生层次但写明「在校大学生/在校生」-> 按本科生四档补齐（不加研究生，避免误放）
    undergrad = any(t in out for t in ("大一", "大二", "大三", "大四")) or re.search(r"本.{0,2}科", s2)
    if not undergrad and ("在校大学生" in s2 or "在校生" in s2 or "大学生" in s2):
        for t in ("大一", "大二", "大三", "大四"):
            if t not in out:
                out.append(t)
    order = {"大一": 0, "大二": 1, "大三": 2, "大四": 3, "研究生": 4, "其他": 5}
    return sorted(set(out), key=lambda t: order.get(t, 9))


def split_list(text) -> list:
    """顿号/逗号分隔文本 -> 去重数组。"""
    s = str(text or "").strip()
    if not s or s in ("待确认", "无", "暂无"):
        return []
    for ch in "，,;；/|":
        s = s.replace(ch, "、")
    out = []
    for x in s.split("、"):
        x = x.strip()
        if x and x not in out:
            out.append(x)
    return out


def norm_deadline(v, cid: str, col: str, warnings: list) -> str:
    """datetime 或文本 -> ISO8601（北京时间）；无法解析 -> 原文并告警。"""
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        return f"{v:%Y-%m-%dT%H:%M}:00+08:00"
    s = str(v).strip()
    if not s:
        return ""
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})", s)
    if m:
        y, mo, d, h, mi = (int(x) for x in m.groups())
        if h == 24:  # 「24:00」归一为次日 00:00
            dt = datetime(y, mo, d) + timedelta(days=1)
            return f"{dt:%Y-%m-%d}T00:00:00+08:00"
        return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:00+08:00"
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}T00:00:00+08:00"
    if re.search(r"待确认|另查|以.*为准", s):
        return ""
    warnings.append(f"{cid}.{col}: 无法解析截止时间「{s[:40]}」，置空")
    return ""


def map_status(raw, cid: str, warnings: list) -> str:
    s = str(raw or "").strip()
    if s in VALID_STATUS:
        return s
    if s:
        warnings.append(f"{cid}.status: 「{s}」不在状态枚举，归一为「待确认」")
    return "待确认"


def map_link(raw) -> str:
    """notice_status/registration_status -> 契约值；已发布/报名中等 -> 待确认。"""
    s = str(raw or "").strip()
    return s if s in LINK_CONTRACT else "待确认"


def truncate_reason(cid: str, reason, warnings: list):
    reason = (reason or "").replace("\n", "").replace("\r", "").strip()
    if not reason or reason in ("待确认", "无", "暂无"):
        return None
    if len(reason) < 30:
        warnings.append(f"{cid}: 推荐理由仅{len(reason)}字（规则要求30-150），建议复核补充")
        return reason
    if len(reason) <= 150:
        return reason
    head = reason[:150]
    cut = max(head.rfind("。"), head.rfind("；"), head.rfind(";"), head.rfind("，"))
    head = head[:cut] if cut >= 60 else head
    warnings.append(f"{cid}: 推荐理由{len(reason)}字超过150上限，已按句截断为{len(head) + 1}字")
    return head + "…"


def load_rows(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[SHEET]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h).strip() if h is not None else None for h in rows[HEADER_ROW - 1]]
    out = []
    for r in rows[HEADER_ROW:]:
        if r[0] is None:
            continue
        out.append({h: v for h, v in zip(hdr, r) if h})
    return out


def main():
    xlsx = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    if not os.path.exists(xlsx):
        raise SystemExit(f"找不到 Excel：{xlsx}")
    data = load_rows(xlsx)

    warnings: list = []
    inserted, updated, deleted, skipped = [], [], [], []

    conn = sqlite3.connect(DB)
    existing = {r[0] for r in conn.execute("SELECT id FROM contests")}

    for row in data:
        cid = str(row.get("competition_id") or "").strip()
        if not cid:
            continue
        review = str(row.get("data_review_status") or "").strip()

        if review == "需补充":
            if cid in existing:
                conn.execute("DELETE FROM contests WHERE id=?", (cid,))
                deleted.append(cid)
            else:
                deleted.append(f"{cid}(库中不存在,跳过删除)")
            continue
        if review not in ("可录入", "已录入"):
            skipped.append(f"{cid}({review or '状态为空'})")
            continue

        # ---- 字段归一 ----
        grades = parse_grades(row.get("eligible_grades"))
        if not grades:
            warnings.append(f"{cid}: eligible_grades 原文无法解析为年级枚举，置 []（资格待确认）")
        reason = truncate_reason(cid, normalize_recommended_major_reason(
            row.get("recommended_major_reason")), warnings)
        majors = normalize_recommended_majors(row.get("recommended_majors"))
        if not majors:
            warnings.append(f"{cid}: recommended_majors 为空（推荐专业待确认，不影响报名）")
        note_parts = [
            str(row.get(k) or "").strip()
            for k in ("review_note", "review_comment")
        ]
        merged_note = "；".join(p for p in note_parts if p)
        link_status = {
            "notice": map_link(row.get("notice_status")),
            "registration": map_link(row.get("registration_status")),
        }
        values = {
            "name": str(row.get("competition_name") or "").strip(),
            "session": str(row.get("session") or "").strip(),
            "category": str(row.get("category") or "").strip(),
            "tags": json.dumps(split_list(row.get("tags")), ensure_ascii=False),
            "organizer": str(row.get("organizer") or "").strip(),
            "eligible_grades": json.dumps(grades, ensure_ascii=False),
            "major_limit": str(row.get("major_limit") or "").strip() or "待确认",
            "recommended_majors": json.dumps(majors, ensure_ascii=False),
            "recommended_major_reason": reason,
            "school_limit": str(row.get("school_limit") or "").strip() or "待确认",
            "registration_deadline": norm_deadline(
                row.get("registration_deadline"), cid, "registration_deadline", warnings),
            "registration_deadline_note": str(row.get("registration_deadline_note") or "").strip(),
            "submission_deadline": norm_deadline(
                row.get("submission_deadline"), cid, "submission_deadline", warnings),
            "submission_deadline_note": str(row.get("submission_deadline_note") or "").strip(),
            "materials": str(row.get("materials") or "").strip(),
            "process": str(row.get("process") or "").strip(),
            "skills": str(row.get("skills") or "").strip(),
            "outcomes": str(row.get("outcomes") or "").strip(),
            "ability_training": str(row.get("ability_training") or "").strip(),
            "estimated_time": str(row.get("estimated_time") or "").strip(),
            "notice_url": str(row.get("notice_url") or "").strip(),
            "registration_url": str(row.get("registration_url") or "").strip(),
            "source_type": str(row.get("source_type") or "其他").strip(),
            "verified_at": norm_deadline(row.get("verified_at"), cid, "verified_at", warnings)[:10],
            "status": map_status(row.get("status"), cid, warnings),
            "link_status": json.dumps(link_status, ensure_ascii=False),
            "review_note": merged_note,
        }
        if values["source_type"] not in ("官网", "百度百科", "转载", "其他"):
            warnings.append(f"{cid}.source_type: 「{values['source_type']}」非法，归一为「其他」")
            values["source_type"] = "其他"

        if cid in existing:
            sets = ", ".join(f"{f}=?" for f in FIELDS)
            conn.execute(
                f"UPDATE contests SET {sets} WHERE id=?",
                [values[f] for f in FIELDS] + [cid],
            )
            updated.append(cid)
        else:
            cols = ["id"] + FIELDS
            conn.execute(
                f"INSERT INTO contests ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})",
                [cid] + [values[f] for f in FIELDS],
            )
            inserted.append(cid)

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM contests").fetchone()[0]
    ids = [r[0] for r in conn.execute("SELECT id FROM contests ORDER BY id")]
    conn.close()

    lines = [
        f"来源文件: {xlsx}",
        f"Excel 记录数: {len(data)}",
        f"新增 {len(inserted)} 条: {inserted}",
        f"更新 {len(updated)} 条: {updated}",
        f"删除(需补充) {len([d for d in deleted if '跳过' not in d])} 条: {deleted}",
        f"跳过 {len(skipped)} 条: {skipped}",
        f"数据库现有 {total} 条: {ids}",
        "",
        "---- 告警 ----",
    ]
    lines += [f"WARN: {w}" for w in warnings] or ["(无)"]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"inserted={len(inserted)} updated={len(updated)} deleted={len(deleted)} skipped={len(skipped)}")
    print(f"db_total={total}")
    print(f"warnings={len(warnings)} (details in {os.path.basename(REPORT)})")


if __name__ == "__main__":
    main()
