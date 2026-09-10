#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对比文博卉新Excel与数据库差异，生成修正报告。

对比维度：
1. major_limit：是否使用10个标准专业大类词表
2. notice_url/registration_url：是否有效URL（非链接文字应清空）
3. status：是否根据"官方报名入口状态"更新
4. registration_deadline：是否缺失或需要更新
5. link_status：是否根据报名入口状态更新
6. 其他字段：materials/process/skills/outcomes/review_note等是否需要更新
"""
import sqlite3
import openpyxl
import re
import json

DB = r"d:\contest-hub\contests.db"
XLSX = r"C:\Users\Lenovo\Documents\xwechat_files\wxid_xiyy9d1l0ic222_0726\msg\file\2026-09\文第一天交付修改A版（按十项分类）.xlsx"

# 10个标准专业大类
VALID_MAJORS = {"计算机", "电子信息", "经管", "设计", "机械", "材料", "理学", "文法", "医学", "其他", "不限"}

URL_RE = re.compile(r"https?://[^\s，。、；;）)\"'<>]+")


def is_url(s):
    if not s:
        return False
    return bool(s.strip().lower().startswith(("http://", "https://")))


def extract_url(s):
    if not s:
        return ""
    m = URL_RE.search(s)
    return m.group(0).rstrip(".,。") if m else ""


# Excel"官方报名入口状态" -> 数据库status映射
ENTRY_STATUS_MAP = {
    "已开放": "报名中",
    "部分校已开放": "报名中",
    "未开放": "待确认",
    "已结束征集": "已截止",
    "已结束": "已截止",
}


def map_entry_status(raw):
    """从Excel'官方报名入口状态'列解析状态。"""
    if not raw:
        return "待确认"
    for key, val in ENTRY_STATUS_MAP.items():
        if key in raw:
            return val
    return "待确认"


# 读取Excel
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active

# 读表头
headers = [cell.value for cell in ws[1]]
hidx = {h: i for i, h in enumerate(headers) if h}

# 读取数据库
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM contests ORDER BY id")
db_rows = {r["id"]: r for r in cur.fetchall()}
conn.close()

issues = []

for row in ws.iter_rows(min_row=2, values_only=True):
    seq = row[hidx["序号"]]
    cid = f"imp_{seq:03d}"
    db = db_rows.get(cid)
    if not db:
        issues.append(f"[{cid}] 数据库中不存在（新增？）")
        continue

    name = row[hidx["竞赛名称"]]
    major_raw = row[hidx["适配专业"]] or ""
    notice_raw = row[hidx["官方通知URL"]] or ""
    reg_raw = row[hidx["报名链接"]] or ""
    entry_status_raw = row[hidx["官方报名入口状态"]] or ""
    deadline_raw = row[hidx["报名截止(本届)"]] or ""
    verified_raw = row[hidx["最近核查"]] or ""
    status_raw = row[hidx["状态"]] or ""

    row_issues = []

    # 1. major_limit
    db_major = db["major_limit"] or ""
    if db_major != major_raw:
        # 检查DB中是否有非标准词
        if db_major != "不限":
            db_parts = [p.strip() for p in db_major.split(",") if p.strip()]
            non_standard = [p for p in db_parts if p not in VALID_MAJORS]
            if non_standard:
                row_issues.append(f"major_limit 不标准: DB='{db_major}' -> Excel='{major_raw}' (含非标准词: {non_standard})")
            elif db_major != major_raw:
                row_issues.append(f"major_limit 不一致: DB='{db_major}' -> Excel='{major_raw}'")

    # 2. notice_url
    db_notice = db["notice_url"] or ""
    if not is_url(db_notice) and db_notice:
        row_issues.append(f"notice_url 非URL: DB='{db_notice[:50]}' -> 应清空或提取")
    extracted = extract_url(notice_raw)
    if extracted and extracted != db_notice:
        row_issues.append(f"notice_url 需更新: DB='{db_notice[:40]}' -> Excel提取='{extracted[:40]}'")
    elif not is_url(db_notice) and not extracted and notice_raw:
        row_issues.append(f"notice_url Excel也非URL: '{notice_raw[:40]}' -> 应清空")

    # 3. registration_url
    db_reg = db["registration_url"] or ""
    if not is_url(db_reg) and db_reg:
        row_issues.append(f"registration_url 非URL: DB='{db_reg[:50]}' -> 应清空")
    extracted_reg = extract_url(reg_raw)
    if extracted_reg and extracted_reg != db_reg:
        row_issues.append(f"registration_url 需更新: DB='{db_reg[:40]}' -> Excel提取='{extracted_reg[:40]}'")
    elif not is_url(db_reg) and not extracted_reg and reg_raw:
        row_issues.append(f"registration_url Excel也非URL: '{reg_raw[:40]}' -> 应清空")

    # 4. status
    new_status = map_entry_status(entry_status_raw)
    if db["status"] != new_status:
        row_issues.append(f"status: DB='{db['status']}' -> 新'{new_status}' (依据: 官方报名入口状态='{entry_status_raw}')")

    # 5. registration_deadline
    db_deadline = db["registration_deadline"] or ""
    if not db_deadline:
        row_issues.append(f"registration_deadline 缺失: Excel='{deadline_raw[:50]}'")

    # 6. link_status
    db_link = json.loads(db["link_status"] or '{"notice":"待确认","registration":"待确认"}')
    # 根据报名入口状态推断link_status
    if "已开放" in entry_status_raw:
        new_link_reg = "可用" if is_url(extracted_reg) or is_url(reg_raw) else "待确认"
    elif "已结束" in entry_status_raw:
        new_link_reg = "失效"
    else:
        new_link_reg = "待确认"
    new_link_notice = "可用" if is_url(extracted) or is_url(notice_raw) else "待确认"

    if db_link.get("notice") != new_link_notice or db_link.get("registration") != new_link_reg:
        row_issues.append(
            f"link_status: DB={db_link} -> 新={{notice:'{new_link_notice}', registration:'{new_link_reg}'}}"
        )

    # 7. verified_at
    db_verified = db["verified_at"] or ""
    excel_verified = str(verified_raw).replace("/", "-") if verified_raw else ""
    if excel_verified and db_verified != excel_verified:
        row_issues.append(f"verified_at: DB='{db_verified}' -> Excel='{excel_verified}'")

    # 8. 新字段数据
    ideal = row[hidx.get("适配理想/目标", -1)] or ""
    if ideal and not db["skills"]:
        row_issues.append(f"skills 缺失，Excel适配理想/目标='{ideal[:40]}'")
    value = row[hidx.get("竞赛自身价值(客观)", -1)] or ""
    if value and not db["outcomes"]:
        row_issues.append(f"outcomes 缺失，Excel竞赛自身价值='{value[:40]}'")
    school_note = row[hidx.get("学校认定说明(已核实才录入)", -1)] or ""
    if school_note and not db["review_note"]:
        row_issues.append(f"review_note 缺失，Excel学校认定说明='{school_note[:40]}'")
    materials = row[hidx.get("需准备材料", -1)] or ""
    if materials and not db["materials"]:
        row_issues.append(f"materials 缺失")
    process = row[hidx.get("提交流程", -1)] or ""
    if process and not db["process"]:
        row_issues.append(f"process 缺失")
    grade_level = row[hidx.get("比赛等级", -1)] or ""
    if grade_level:
        row_issues.append(f"比赛等级(新): '{grade_level[:30]}' -> 需存入category或tags")

    if row_issues:
        issues.append(f"\n{'='*60}")
        issues.append(f"[{cid}] {name[:25]}")
        for iss in row_issues:
            issues.append(f"  - {iss}")

print("\n".join(issues))
print(f"\n{'='*60}")
print(f"共 {len(issues)} 条问题")
