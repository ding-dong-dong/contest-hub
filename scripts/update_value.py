#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从田淋元价值判定表更新数据库。

更新项：
1. skills <- skills列（能力关键词）
2. outcomes <- outcomes列（成果产出，替换之前的目标文本）
3. estimated_time <- estimated_time列（标准化时间档位：≤3/4-7/8-14/≥15）
4. review_note <- 合并：能力依据 + 成果依据 + 投入依据 + 学分认定 + 认定依据
5. notice_url <- 来源链接列（提取URL）
6. verified_at <- 核查时间列
7. ability_training 保留不变（上一版已填入，本表无此列）
"""
import json
import re
import sqlite3

import openpyxl

DB = r"d:\contest-hub\contests.db"
XLSX = r"d:\contest-hub\scripts\_value_excel.xlsx"

URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+")


def extract_url(raw):
    if not raw:
        return ""
    raw = str(raw).strip()
    m = URL_RE.search(raw)
    if m:
        return m.group(0).rstrip(".,。")
    return ""


wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active
headers = [cell.value for cell in ws[1]]
hidx = {h: i for i, h in enumerate(headers) if h}

conn = sqlite3.connect(DB)
cur = conn.cursor()

changes = []

for row in ws.iter_rows(min_row=2, values_only=True):
    seq = row[hidx["序号"]]
    cid = f"imp_{seq:03d}"

    skills_new = row[hidx["skills（能力，用「、」分隔）"]] or ""
    outcomes_new = row[hidx["outcomes（成果，用「、」分隔）"]] or ""
    time_new = row[hidx["estimated_time（≤3 / 4-7 / 8-14 / ≥15 小时/周）"]] or ""
    ability_evidence = row[hidx["能力依据（官方通知里的栏目/原文位置）"]] or ""
    outcomes_evidence = row[hidx["成果依据（官方通知「提交材料」部分）"]] or ""
    time_evidence = row[hidx["投入依据（官方赛程/往届流程/可靠访谈）"]] or ""
    credit = row[hidx["学分/综测认定（写适用学校和状态）"]] or ""
    credit_evidence = row[hidx["认定依据（学校正式文件链接，没有留空）"]] or ""
    source_url = row[hidx["来源链接（优先官方通知）"]] or ""
    verified = row[hidx["核查时间"]] or ""
    review_status = row[hidx["复核状态（待审核/可录入/需补充/已录入）"]] or ""

    # 提取URL
    notice_url = extract_url(source_url)

    # 构建review_note：合并所有依据
    parts = []
    if ability_evidence:
        parts.append(f"能力依据: {ability_evidence}")
    if outcomes_evidence:
        parts.append(f"成果依据: {outcomes_evidence}")
    if time_evidence:
        parts.append(f"投入依据: {time_evidence}")
    if credit:
        parts.append(f"学分认定: {credit}")
    if credit_evidence:
        parts.append(f"认定依据: {credit_evidence}")
    if review_status:
        parts.append(f"复核状态: {review_status}")
    review_note = "\n".join(parts)

    # 标准化estimated_time
    time_new = str(time_new).strip()

    cur.execute(
        """UPDATE contests SET
            skills=?, outcomes=?, estimated_time=?,
            review_note=?, notice_url=?, verified_at=?
        WHERE id=?""",
        (skills_new, outcomes_new, time_new, review_note, notice_url, str(verified), cid),
    )

    changes.append(
        f"[{cid}] skills='{skills_new[:20]}' outcomes='{outcomes_new[:20]}' "
        f"time='{time_new}' url={'有' if notice_url else '空'} verified='{verified}'"
    )

conn.commit()

# 验证
cur.execute("SELECT id, outcomes, estimated_time FROM contests WHERE id LIKE 'imp_%' LIMIT 5")
print("=== 验证前5条 ===")
for r in cur.fetchall():
    print(f"  {r[0]}: outcomes='{r[1][:30]}' time='{r[2]}'")

cur.execute("SELECT COUNT(*) FROM contests WHERE estimated_time != '' AND estimated_time IS NOT NULL")
has_time = cur.fetchone()[0]
print(f"\n有 estimated_time 的记录: {has_time}/15")

conn.close()
print("\n更新完成:")
for c in changes:
    print(c)
