#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""导入文博卉《推荐专业数据表_B版》到 contests.db（可重复执行的 upsert）。

数据依据：田淋元《推荐专业规则与验收清单 V1.0》
- major_limit 保留官方原文（不限专业/待确认/原文摘录），不改写为推荐专业
- recommended_majors 归一为 10 枚举 JSON 数组；「待确认」-> []
- recommended_major_reason 30-150 字；「待确认」-> None；超长按句截断并告警
- 旧 15 条：更新名称/状态/专业限制/价值字段/推荐专业；保留已人工校订的截止日期等
- 新 15 条（imp_016~030）：整行插入

用法：
    python scripts/import_b_version.py [xlsx路径]
"""
import json
import os
import re
import sqlite3
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.schemas import normalize_recommended_majors, normalize_recommended_major_reason  # noqa: E402

DEFAULT_XLSX = (
    r"C:\Users\Lenovo\Documents\xwechat_files\wxid_xiyy9d1l0ic222_0726"
    r"\msg\file\2026-09\推荐专业数据表_B版_20260911.xlsx"
)
DB = os.path.join(ROOT, "contests.db")
TODAY = (2026, 9, 11)  # 数据核查日，用于判断「未来截止日期」

# 新增竞赛的业务分类（对齐现有 category 取值）
NEW_CATEGORY = {
    "imp_016": "学术科技", "imp_017": "综合", "imp_018": "AI/编程", "imp_019": "AI/编程",
    "imp_020": "创新创业", "imp_021": "综合", "imp_022": "学术科技", "imp_023": "学术科技",
    "imp_024": "学术科技", "imp_025": "学术科技", "imp_026": "综合", "imp_027": "综合",
    "imp_028": "语言文化", "imp_029": "创新创业", "imp_030": "综合",
}

COL_STATUS = "报名状态（正在报名 / 即将开始 / 本届已截止 / 通知未发布）"
COL_DEADLINE = "报名截止(本届)"
COL_MAJORS = "recommended_majors（多个专业用中文顿号分隔；待确认时写「待确认」；导入 API 时转为 []）"
COL_REASON = "recommended_major_reason（30–150 字完整说明，基于比赛任务、提交材料或评审标准）"
COL_SKILLS = "skills（能力，用「、」分隔）"
COL_OUTCOMES = "outcomes（成果，用「、」分隔）"
COL_TIME = "estimated_time（≤3 / 4-7 / 8-14 / ≥15 小时/周）"


def map_status(raw: str) -> str:
    """B版报名状态 -> 前端状态枚举。"""
    s = str(raw or "")
    if "正在报名" in s:
        return "报名中"
    if "即将截止" in s:
        return "即将截止"
    if "已截止" in s and ("下届" in s or "即将启动" in s or "即将开始" in s):
        return "待确认"  # 本届已截止但下届将启动，报名口径待确认
    if "已截止" in s:
        return "已截止"
    if "即将开始" in s or "即将启动" in s:
        return "待确认"
    if "通知未发布" in s or "通知已发布" in s:
        return "待确认"
    return "待确认"


_DATE_RE = re.compile(r"(\d{4})\s*[年.\-/]\s*(\d{1,2})\s*[月.\-/]\s*(\d{1,2})")
_TIME_RE = re.compile(r"(\d{1,2})\s*时(?:(\d{2})\s*分)?")


def parse_future_deadline(text: str):
    """从自由文本中提取不早于核查日的首个明确日期 -> ISO8601（北京时间）。"""
    dates = []
    for m in _DATE_RE.finditer(str(text or "")):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mo <= 12 and 1 <= d <= 31):
            continue
        tail = str(text or "")[m.end():m.end() + 8]
        tm = _TIME_RE.search(tail)
        hh = int(tm.group(1)) if tm else 12
        mm = int(tm.group(2)) if tm and tm.group(2) else 0
        dates.append(((y, mo, d), f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:00+08:00"))
    future = [iso for key, iso in dates if key >= TODAY]
    return future[0] if future else ""


def map_effort(raw: str) -> str:
    m = re.search(r"≥15|8-14|4-7|≤3", str(raw or ""))
    return m.group(0) if m else ""


def truncate_reason(cid: str, reason: str, warnings: list):
    reason = (reason or "").replace("\n", "").replace("\r", "").strip()
    if not reason or reason == "待确认":
        return None
    if len(reason) < 30:
        warnings.append(f"{cid}: 推荐理由仅{len(reason)}字（规则要求30-150），建议田淋元复核补充")
        return reason
    if len(reason) <= 150:
        return reason
    head = reason[:150]
    cut = max(head.rfind("。"), head.rfind("；"), head.rfind(";"), head.rfind("，"))
    head = head[:cut] if cut >= 60 else head
    warnings.append(f"{cid}: 推荐理由{len(reason)}字超过150上限，已截断为{len(head)+1}字（数据侧应退回文博卉精简）")
    return head + "…"


def source_type_for(url: str) -> str:
    u = str(url or "")
    if "qq.com" in u or "saikr.com" in u or "sohu.com" in u:
        return "转载"
    return "官网" if u.startswith("http") else "其他"


def load_sheets(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    def sheet_dicts(name):
        ws = wb[name]
        rows = list(ws.iter_rows(values_only=True))
        hdr = rows[0]
        return [dict(zip(hdr, r)) for r in rows[1:] if r[0]]

    s1 = {r["competition_id"]: r for r in sheet_dicts("竞赛基础资料")}
    s2 = {r["competition_id"]: r for r in sheet_dicts("价值判定")}
    s3 = {r["competition_id"]: r for r in sheet_dicts("推荐专业")}
    return s1, s2, s3


def main():
    xlsx = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    if not os.path.exists(xlsx):
        raise SystemExit(f"找不到 Excel：{xlsx}")
    s1, s2, s3 = load_sheets(xlsx)

    review_warning = sorted({
        cid for cid, r in s1.items() if str(r.get("review_status") or "") != "可录入"
    })
    warnings = []
    if review_warning:
        warnings.append(
            f"全部{len(review_warning)}条记录复核状态均非「可录入」（{len(review_warning)}条为待审核），"
            f"按V1.0规则本批数据应在田淋元复核通过后再正式生效；本次按陈玉婷要求先行录入，复核后请重跑本脚本"
        )

    conn = sqlite3.connect(DB)
    existing = {r[0] for r in conn.execute("SELECT id FROM contests")}
    inserted, updated = [], []

    for cid in sorted(s1):
        a, b, c = s1[cid], s2.get(cid, {}), s3.get(cid, {})
        name = str(a["competition_name"]).strip()
        status = map_status(a.get(COL_STATUS))
        major_limit = str(a.get("major_limit") or "待确认").strip() or "待确认"
        url = str(a.get("evidence_url") or "").strip()
        verified = str(a.get("verified_at") or "").strip()
        skills = str(b.get(COL_SKILLS) or "").strip()
        outcomes = str(b.get(COL_OUTCOMES) or "").strip()
        effort = map_effort(b.get(COL_TIME))
        majors = normalize_recommended_majors(c.get(COL_MAJORS))
        reason = truncate_reason(cid, normalize_recommended_major_reason(c.get(COL_REASON)), warnings)

        if cid in existing:
            # 旧竞赛：只更新 B版权威字段，保留人工校订的截止日期/分类/材料等
            conn.execute(
                """UPDATE contests SET name=?, status=?, major_limit=?, skills=?, outcomes=?,
                   estimated_time=COALESCE(NULLIF(?, ''), estimated_time), verified_at=?,
                   recommended_majors=?, recommended_major_reason=? WHERE id=?""",
                (name, status, major_limit, skills, outcomes, effort, verified,
                 json.dumps(majors, ensure_ascii=False), reason, cid),
            )
            if url.startswith("http"):
                conn.execute(
                    "UPDATE contests SET notice_url=? WHERE id=? AND (notice_url IS NULL OR notice_url='' OR notice_url NOT LIKE 'http%')",
                    (url, cid),
                )
            updated.append(cid)
            continue

        # 新竞赛：整行插入
        deadline_note = str(a.get(COL_DEADLINE) or "").strip()
        deadline = parse_future_deadline(deadline_note) if status in ("报名中", "即将截止") else ""
        conn.execute(
            """INSERT INTO contests (
                id, name, session, category, tags, organizer, eligible_grades, major_limit,
                school_limit, registration_deadline, registration_deadline_note,
                submission_deadline, submission_deadline_note, materials, process,
                skills, outcomes, ability_training, estimated_time, notice_url,
                registration_url, source_type, verified_at, status, link_status, review_note,
                recommended_majors, recommended_major_reason
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cid, name, str(a.get("比赛周期(本届)") or "").strip(), NEW_CATEGORY[cid], "[]", "", "[]",
                major_limit, "待确认", deadline, deadline_note, "", "", "", "",
                skills, outcomes, "", effort, url, "", source_type_for(url),
                verified, status, '{"notice": "待确认", "registration": "待确认"}',
                str(a.get("review_comment（问题或补充说明）") or "").strip(),
                json.dumps(majors, ensure_ascii=False), reason,
            ),
        )
        inserted.append(cid)

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM contests").fetchone()[0]
    conn.close()

    print(f"新增 {len(inserted)} 条：{inserted}")
    print(f"更新 {len(updated)} 条：{updated}")
    print(f"数据库现有 {total} 条")
    for w in warnings:
        print("WARN:", w)


if __name__ == "__main__":
    main()
