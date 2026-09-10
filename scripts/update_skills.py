#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从新版Excel（含技能分析）更新数据库。

更新项：
1. skills <- 技能需求（关键词列表）
2. ability_training <- 能力训练说明（详细描述）[新字段]
3. tags 加入场景标签（首次参赛/已有目标/时间有限/重视认定）
4. tags 保留原有比赛等级标签
"""
import json
import sqlite3
import re

import openpyxl

DB = r"d:\contest-hub\contests.db"
XLSX = r"d:\contest-hub\scripts\_new_excel.xlsx"


def extract_grade_tags(raw):
    """从比赛等级提取简短标签。"""
    if not raw:
        return []
    raw = str(raw)
    tags = []
    if "A+" in raw:
        tags.append("A+级")
    elif "A类" in raw:
        tags.append("A类")
    if "白名单" in raw:
        tags.append("白名单")
    if "专项赛" in raw:
        tags.append("专项赛")
    if "省级" in raw:
        tags.append("省级")
    if "传统赛事" in raw:
        tags.append("传统赛事")
    return tags


def map_scene_tag(val):
    """将场景适配列的值映射为简短标签。"""
    if not val:
        return None
    val = str(val)
    if "适配" in val:
        return "适配"
    if "不适配" in val:
        return "不适配"
    return None


wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb.active
headers = [cell.value for cell in ws[1]]
hidx = {h: i for i, h in enumerate(headers) if h}

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 先检查 ability_training 列是否存在
cur.execute("PRAGMA table_info(contests)")
cols = [row[1] for row in cur.fetchall()]
if "ability_training" not in cols:
    cur.execute("ALTER TABLE contests ADD COLUMN ability_training TEXT DEFAULT ''")
    print("新增 ability_training 列")

changes_log = []

for row in ws.iter_rows(min_row=2, values_only=True):
    seq = row[hidx["序号"]]
    cid = f"imp_{seq:03d}"

    skills_new = row[hidx["技能需求"]] or ""
    ability_new = row[hidx["能力训练说明"]] or ""
    grade_raw = row[hidx["比赛等级"]] or ""

    # 场景标签
    scene_tags = []
    for col_name, label in [("首次参赛", "首次参赛"), ("已有目标", "已有目标"), ("时间有限", "时间有限"), ("重视认定", "重视认定")]:
        if col_name in hidx:
            val = row[hidx[col_name]]
            mapped = map_scene_tag(val)
            if mapped == "适配":
                scene_tags.append(f"{label}适配")
            elif mapped == "不适配":
                scene_tags.append(f"{label}不适配")

    # 合并比赛等级标签 + 场景标签
    grade_tags = extract_grade_tags(grade_raw)
    all_tags = grade_tags + scene_tags

    cur.execute(
        "UPDATE contests SET skills=?, ability_training=?, tags=? WHERE id=?",
        (skills_new, ability_new, json.dumps(all_tags, ensure_ascii=False), cid),
    )

    changes_log.append(
        f"[{cid}] skills='{skills_new[:25]}' "
        f"ability='{ability_new[:25]}' "
        f"tags={all_tags}"
    )

conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM contests")
print(f"更新完成，共 {cur.fetchone()[0]} 条记录")
for log in changes_log:
    print(log)

conn.close()
