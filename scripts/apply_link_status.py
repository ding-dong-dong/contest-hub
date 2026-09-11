#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""链接修复与状态回写（陈玉婷｜2026-09-11）。

背景：总表导入时 notice_status/registration_status（已发布/报名中…）不符合
link_status 契约枚举（可用/失效/待确认），被保守置为「待确认」，前端把链接
全部置灰不可点；另发现 2 处脏链接（imp_009 邮箱误入 URL 字段、imp_014 链接带
中文备注）和 1 个失效裸链接（imp_009 百度百科 /item/ 404）。

本脚本（可重复执行）：
  1. 特殊修正（见 SPECIAL_FIXES）：替换失效链接、清空非链接内容、剔除尾部备注；
  2. 对每个非空链接做 HTTP 可达性核查（复用 check_links 的 normalize/check）；
  3. 回写 link_status：200（含证书异常但可达）-> 可用；4xx/5xx/不可达 -> 失效；
     空链接 -> 待确认；
  4. 清洗与修正动作以「【链接修复20260911】」标签追加到 review_note（重跑先去旧标签）；
  5. 生成 scripts/link_fix_report.txt（UTF-8）。

用法：
    .venv\\Scripts\\python.exe scripts/apply_link_status.py
"""
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from check_links import check_one, normalize_url  # noqa: E402

DB = ROOT / "contests.db"
REPORT = ROOT / "scripts" / "link_fix_report.txt"
TAG = "【链接修复20260911】"

# 列名 -> link_status JSON 键
KIND_COL = {"notice": "notice_url", "reg": "registration_url"}
KIND_KEY = {"notice": "notice", "reg": "registration"}

# 人工确认的特殊修正（2026-09-11 已逐一验证）：(cid, kind) -> (新URL或'', 留痕说明)
SPECIAL_FIXES = {
    ("imp_009", "notice"): (
        "https://szysycm.sdada.edu.cn/info/1337/3401.htm",
        "原百度百科裸链接 /item/ 返回404，改挂山东艺术学院官网转发的本届征集启事（HTTP 200），来源由百度百科变更为转载",
    ),
    ("imp_009", "reg"): (
        "",
        "该赛项为邮件投稿（shixie_dspds@163.com 上海视协征稿专用邮箱），无在线报名入口，报名链接置空、状态待确认",
    ),
    ("imp_014", "notice"): (
        "http://nuedc.xjtu.edu.cn/",
        "剔除链接尾部中文备注「（组委会通知待确认）」；https 握手失败(SSLEOFError)，改用可达的 http 地址（HTTP 200）",
    ),
}

# 特殊修正附带的字段更新：cid -> {列: 新值}
SPECIAL_FIELD_UPDATE = {
    "imp_009": {
        "source_type": "转载",
        "process": "“看见美丽中国”主题短视频发送至征稿邮箱 shixie_dspds@163.com（上海视协征稿专用邮箱）投稿→征集→初评/终评→表彰/展播。时长、格式、附件及报名入口待确认。",
    },
}


def _strip_tag(note: str) -> str:
    """重跑幂等：去掉上一次追加的修复标签段落。"""
    note = note or ""
    return re.sub(r"\s*【链接修复20260911】.*?(?=；【|$)", "", note).strip("； ")


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM contests")}

    report = []
    stats = {"可用": 0, "失效": 0, "待确认": 0}
    changes = []

    for cid in sorted(rows):
        r = rows[cid]
        link_status = json.loads(r["link_status"] or '{"notice": "待确认", "registration": "待确认"}')
        fix_notes = []
        url_updates = {}
        field_updates = dict(SPECIAL_FIELD_UPDATE.get(cid, {}))

        for kind, col in KIND_COL.items():
            raw = str(r.get(col) or "")
            # 1) 特殊修正
            if (cid, kind) in SPECIAL_FIXES:
                new_url, why = SPECIAL_FIXES[(cid, kind)]
                if raw.strip() != new_url:
                    url_updates[col] = new_url
                    fix_notes.append(why)
                raw = new_url
            # 2) 归一化（剔除尾部备注、提取混排链接）
            if raw:
                url, prep = normalize_url(raw)
                if url and url != raw.strip():
                    url_updates[col] = url
                    fix_notes.append(f"{col} 自动清洗：{prep}")
                    raw = url
                elif prep and (cid, kind) not in SPECIAL_FIXES:
                    # normalize 提取了链接但原值非标准开头
                    if url:
                        url_updates[col] = url
                        fix_notes.append(f"{col} 自动清洗：{prep}")
                        raw = url
            # 3) HTTP 核查 -> 状态
            if not raw:
                status = "待确认"
                detail = "空链接"
            else:
                res = check_one(raw)
                if res["status"] == 200:
                    status = "可用"
                    detail = res["note"] or "HTTP 200"
                else:
                    status = "失效"
                    detail = f"{res['note']} HTTP={res['status']}"
            link_status[KIND_KEY[kind]] = status
            stats[status] += 1
            report.append(f"{cid} {kind:6s} -> {status:3s} | {detail} | {raw or '(空)'}")

        # 4) 回写
        sets = {"link_status": json.dumps(link_status, ensure_ascii=False)}
        sets.update(url_updates)
        sets.update(field_updates)
        # review_note 留痕（幂等）
        if fix_notes:
            base = _strip_tag(r.get("review_note") or "")
            tag_text = TAG + "；".join(dict.fromkeys(fix_notes))
            sets["review_note"] = (base + "；" + tag_text) if base else tag_text
            changes.append(cid)

        assignments = ", ".join(f"{k}=?" for k in sets)
        conn.execute(
            f"UPDATE contests SET {assignments} WHERE id=?",
            list(sets.values()) + [cid],
        )

    conn.commit()
    conn.close()

    header = [
        f"链接修复报告 2026-09-11",
        f"统计：可用 {stats['可用']}，失效 {stats['失效']}，待确认 {stats['待确认']}",
        f"发生修正的竞赛：{sorted(set(changes))}",
        "",
    ]
    REPORT.write_text("\n".join(header + report) + "\n", encoding="utf-8")
    print(f"可用={stats['可用']} 失效={stats['失效']} 待确认={stats['待确认']}")
    print(f"修正竞赛: {sorted(set(changes))}")
    print(f"报告: {REPORT}")


if __name__ == "__main__":
    main()
