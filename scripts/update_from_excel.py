#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从文博卉A版Excel更新数据库15条竞赛记录。

修正项：
1. major_limit -> 用Excel标准10大类词表
2. notice_url/registration_url -> 提取有效URL，非URL文字清空
3. status -> 根据"官方报名入口状态"派生（已开放=报名中/已结束=已截止/未开放=待确认）
4. link_status -> 根据报名入口状态和URL有效性派生
5. skills <- 适配理想/目标
6. outcomes <- 竞赛自身价值(客观)
7. review_note <- 学校认定说明(已核实才录入)
8. materials/process/verified_at/session/school_limit 同步更新
9. tags <- 比赛等级（如"A+级","A类","白名单"）
"""
import json
import re
import sqlite3
import sys
from datetime import date

import openpyxl

DB = r"d:\contest-hub\contests.db"
XLSX = r"C:\Users\Lenovo\Documents\xwechat_files\wxid_xiyy9d1l0ic222_0726\msg\file\2026-09\文第一天交付修改A版（按十项分类）.xlsx"

URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+")


def extract_url(raw):
    if not raw:
        return ""
    raw = str(raw).strip()
    m = URL_RE.search(raw)
    if m:
        url = m.group(0)
        # 截断括号后的附加说明
        url = re.split(r"[\s（(]", url, maxsplit=1)[0].rstrip(".,。")
        return url
    return ""


def map_entry_status(raw):
    if not raw:
        return "待确认"
    if "已结束" in raw:
        return "已截止"
    if "已开放" in raw or "部分校已开放" in raw:
        return "报名中"
    if "未开放" in raw:
        return "待确认"
    return "待确认"


def map_link_status(entry_raw, url):
    """根据报名入口状态和URL有效性推断link_status。"""
    if not url:
        return "待确认"
    if "已结束" in (entry_raw or ""):
        return "失效"
    if "已开放" in (entry_raw or "") or "部分校已开放" in (entry_raw or ""):
        return "可用"
    return "待确认"


def parse_deadline(raw):
    """尝试从文本中提取YYYY-MM-DD格式的截止日期。"""
    if not raw:
        return ""
    raw = str(raw)
    # 优先匹配 2026年X月X日 或 2026-X-X
    m = re.search(r"(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})", raw)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        return f"{y}-{mo:02d}-{d:02d}"
    # 匹配 2026年X月（无具体日，取月底）
    m = re.search(r"(20\d{2})[年\-](\d{1,2})月?", raw)
    if m:
        y, mo = m.group(1), int(m.group(2))
        return f"{y}-{mo:02d}"
    return ""


def extract_grade_level(raw):
    """从'比赛等级'提取简短标签，如 A+级/A类/白名单/专项赛。"""
    if not raw:
        return []
    raw = str(raw)
    tags = []
    if "A+" in raw:
        tags.append("A+级")
    elif "A类" in raw or "A类" in raw:
        tags.append("A类")
    if "白名单" in raw:
        tags.append("白名单")
    if "专项赛" in raw:
        tags.append("专项赛")
    if "省级" in raw:
        tags.append("省级")
    if "传统赛事" in raw:
        tags.append("传统赛事")
    if not tags:
        tags.append(raw[:6])
    return tags


# 读取Excel
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active
headers = [cell.value for cell in ws[1]]
hidx = {h: i for i, h in enumerate(headers) if h}

# 连接数据库
conn = sqlite3.connect(DB)
cur = conn.cursor()

changes_log = []

for row in ws.iter_rows(min_row=2, values_only=True):
    seq = row[hidx["序号"]]
    cid = f"imp_{seq:03d}"

    # 从Excel提取各字段
    name = row[hidx["竞赛名称"]] or ""
    session = row[hidx["本届届次"]] or ""
    grade_level_raw = row[hidx["比赛等级"]] or ""
    major_limit = row[hidx["适配专业"]] or ""
    ideal_goal = row[hidx.get("适配理想/目标", -1)] or ""
    detail_qual = row[hidx.get("详细参赛资格", -1)] or ""
    cycle = row[hidx.get("比赛周期(本届)", -1)] or ""
    deadline_raw = row[hidx["报名截止(本届)"]] or ""
    entry_status_raw = row[hidx["官方报名入口状态"]] or ""
    notice_raw = row[hidx["官方通知URL"]] or ""
    reg_url_raw = row[hidx["报名链接"]] or ""
    materials = row[hidx.get("需准备材料", -1)] or ""
    process = row[hidx.get("提交流程", -1)] or ""
    school_limit = row[hidx["适用学校类别"]] or ""
    value_obj = row[hidx.get("竞赛自身价值(客观)", -1)] or ""
    school_note = row[hidx.get("学校认定说明(已核实才录入)", -1)] or ""
    verified_at = str(row[hidx["最近核查"]] or "").replace("/", "-")
    status_raw = row[hidx["状态"]] or ""

    # 派生字段
    notice_url = extract_url(notice_raw)
    registration_url = extract_url(reg_url_raw)
    status = map_entry_status(entry_status_raw)
    link_notice = map_link_status(entry_status_raw, notice_url)
    link_reg = map_link_status(entry_status_raw, registration_url)
    link_status = json.dumps({"notice": link_notice, "registration": link_reg}, ensure_ascii=False)
    registration_deadline = parse_deadline(deadline_raw)
    tags = extract_grade_level(grade_level_raw)

    # 更新数据库
    cur.execute(
        """UPDATE contests SET
            name=?, session=?, major_limit=?, school_limit=?,
            registration_deadline=?, materials=?, process=?,
            skills=?, outcomes=?, notice_url=?, registration_url=?,
            verified_at=?, status=?, link_status=?, review_note=?, tags=?
        WHERE id=?""",
        (
            name, session, major_limit, school_limit,
            registration_deadline, materials, process,
            ideal_goal, value_obj, notice_url, registration_url,
            verified_at, status, link_status, school_note,
            json.dumps(tags, ensure_ascii=False),
            cid,
        ),
    )

    affected = cur.rowcount
    if affected:
        changes_log.append(
            f"[{cid}] {name[:20]}: "
            f"status={status} major={major_limit[:20]} "
            f"notice={'有' if notice_url else '空'} reg={'有' if registration_url else '空'} "
            f"link=({link_notice}/{link_reg}) deadline={registration_deadline or '无'}"
        )
    else:
        changes_log.append(f"[{cid}] 未找到记录！")

conn.commit()
conn.close()

print(f"更新完成，共 {len(changes_log)} 条：")
for log in changes_log:
    print(log)
