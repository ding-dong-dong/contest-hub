#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理样例数据 + 修正 skills/outcomes 字段映射。

1. 删除 c_001_ai_challenge 和 c_002_biz_plan 两条样例
2. skills/outcomes 内容交换：outcomes 放"适配理想/目标"，organizer 放"竞赛自身价值"
3. link_status 安全降级：空 URL 对应的 link_status 强制为"待确认"
"""
import json
import sqlite3

DB = r"d:\contest-hub\contests.db"
SAMPLE_IDS = ["c_001_ai_challenge", "c_002_biz_plan"]

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 1. 删除样例
for sid in SAMPLE_IDS:
    cur.execute("DELETE FROM contests WHERE id=?", (sid,))
    print(f"删除 {sid}: affected={cur.rowcount}")

# 2. 修正 skills/outcomes/organizer 字段映射
# 当前: skills=适配理想/目标(应放outcomes), outcomes=竞赛自身价值(应放organizer)
# 修正: outcomes<-skills, organizer<-outcomes, skills<-清空(等文博卉补充真实能力训练说明)
cur.execute("SELECT id, skills, outcomes, organizer FROM contests WHERE id LIKE 'imp_%'")
rows = cur.fetchall()
for cid, old_skills, old_outcomes, old_organizer in rows:
    new_outcomes = old_skills or ""      # 适配理想/目标 -> outcomes
    new_organizer = old_outcomes or ""   # 竞赛自身价值 -> organizer
    # skills 暂时清空：当前内容是目标不是能力训练说明，等数据规范后再填
    cur.execute(
        "UPDATE contests SET skills=?, outcomes=?, organizer=? WHERE id=?",
        ("", new_outcomes, new_organizer, cid),
    )
    print(f"修正 {cid}: outcomes<-'{new_outcomes[:20]}' organizer<-'{new_organizer[:20]}'")

# 3. link_status 安全降级：空 URL 的 link_status 强制为"待确认"
cur.execute("SELECT id, notice_url, registration_url, link_status FROM contests")
for cid, notice_url, reg_url, ls_raw in cur.fetchall():
    ls = json.loads(ls_raw or '{"notice":"待确认","registration":"待确认"}')
    changed = False
    if not notice_url or not notice_url.strip().lower().startswith(("http://", "https://")):
        if ls.get("notice") != "待确认":
            ls["notice"] = "待确认"
            changed = True
    if not reg_url or not reg_url.strip().lower().startswith(("http://", "https://")):
        if ls.get("registration") != "待确认":
            ls["registration"] = "待确认"
            changed = True
    if changed:
        cur.execute(
            "UPDATE contests SET link_status=? WHERE id=?",
            (json.dumps(ls, ensure_ascii=False), cid),
        )
        print(f"link_status 降级 {cid}: {ls}")

conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM contests")
print(f"\n清理后数据库共 {cur.fetchone()[0]} 条记录")
cur.execute("SELECT id, skills, outcomes, organizer FROM contests LIMIT 3")
for r in cur.fetchall():
    print(f"  {r[0]}: skills='{r[1][:20]}' outcomes='{r[2][:20]}' organizer='{r[3][:20]}'")

conn.close()
print("\n清理完成")
