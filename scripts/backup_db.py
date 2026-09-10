#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据库备份与恢复（公开演示前的保险措施）。

用法：
  python scripts/backup_db.py                    # 备份当前数据到 backups/ 目录
  python scripts/backup_db.py --restore <文件>   # 用备份 JSON 覆盖当前数据库

备份为 JSON（UTF-8），恢复前会自动把当前数据库再快照一份，防误操作。
"""
import argparse
import json
import os
import shutil
import sqlite3
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "contests.db")
BACKUP_DIR = os.path.join(ROOT, "backups")


def backup() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM contests ORDER BY id")]
    conn.close()
    path = os.path.join(BACKUP_DIR, f"contests_backup_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"已备份 {len(rows)} 条 -> {path}")
    return path


def restore(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        rows = json.load(f)
    if not os.path.exists(DB):
        raise SystemExit(f"数据库不存在: {DB}")
    # 恢复前自动快照当前状态
    os.makedirs(BACKUP_DIR, exist_ok=True)
    pre = os.path.join(BACKUP_DIR, f"contests_pre_restore_{datetime.now():%Y%m%d_%H%M%S}.db")
    shutil.copy2(DB, pre)
    print(f"已快照当前数据库 -> {pre}")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(contests)")]
    cur.execute("DELETE FROM contests")
    for row in rows:
        vals = [row.get(c, "") for c in cols]
        cur.execute(
            f"INSERT INTO contests ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            vals,
        )
    conn.commit()
    cnt = cur.execute("SELECT COUNT(*) FROM contests").fetchone()[0]
    conn.close()
    print(f"已恢复 {cnt} 条记录（来自 {os.path.basename(path)}）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="竞赛数据库备份/恢复")
    parser.add_argument("--restore", metavar="JSON", help="用指定备份 JSON 覆盖当前数据库")
    args = parser.parse_args()
    if args.restore:
        restore(args.restore)
    else:
        backup()
