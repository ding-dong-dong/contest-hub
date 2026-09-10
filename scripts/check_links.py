#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""官方链接自动可达性检测（陈玉婷｜信息维护工具）。

分工依据：
  - 文博卉收集资料并填写官方链接（标记“待审核”）；
  - 田淋元人工复核链接是否为官方页面（标记“可录入/需补充”）；
  - 本脚本只做【技术可达性】预检：自动请求每个链接，看能否打开、返回什么状态，
    生成检测报告交给田淋元/文博卉做人工内容确认，脚本本身不修改数据库。

检测逻辑：
  - 对每条竞赛的 notice_url（官方通知）和 registration_url（报名入口）发 HTTP 请求；
  - 跟随跳转、超时 12 秒、证书错误时降级重试并标注；
  - 结果分三类：
      可访问        HTTP 200（人工仍需确认页面内容是否为官方通知/报名页）
      无法访问      DNS 失败 / 超时 / 连接拒绝 / 4xx-5xx
      无链接        字段为空（报名入口未开放属正常，登记“待确认”即可）

输出：scripts/link_check_report.csv（utf-8-sig，Excel 可直接打开）
      “人工复核结论”列留给田淋元/文博卉填写：可用 / 失效 / 待确认。

用法：
    python scripts/check_links.py
"""
import csv
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, init_db
from app import crud

TIMEOUT = 12
REPORT = Path(__file__).resolve().parent / "link_check_report.csv"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'*+,;=%]+")


def normalize_url(raw: str) -> tuple:
    """返回 (url 或 None, 说明)。处理“URL+中文备注”混排和中文路径。"""
    raw = (raw or "").strip()
    if not raw:
        return None, ""
    note = ""
    if raw.lower().startswith(("http://", "https://")):
        cand = raw
    else:
        m = URL_RE.search(raw)
        if not m:
            return None, f"字段内容不是有效链接（应为空并把情况写入复核备注）：{raw[:50]}"
        cand = m.group(0)
        note = f"字段为说明文字，已从中提取链接：{raw[:50]}"
    # 截断链接后面附带的括号/空格备注，如 “...kdocs.cn/l/xxx(南传报名表)”
    head = re.split(r"[\s（(]", cand, maxsplit=1)[0].rstrip("，。,.")
    if head != cand:
        note += ("；" if note else "") + f"已剔除链接后的附带说明：{cand[len(head):][:40]}"
        cand = head
    # 中文路径（如百度百科词条）做百分号编码
    if any(ord(ch) > 127 for ch in cand):
        try:
            p = urllib.parse.urlsplit(cand)
            netloc = p.netloc
            try:
                netloc = netloc.encode("idna").decode("ascii")
            except Exception:  # noqa: BLE001
                pass
            cand = urllib.parse.urlunsplit(
                (
                    p.scheme,
                    netloc,
                    urllib.parse.quote(p.path, safe="/%"),
                    urllib.parse.quote(p.query, safe="=&%"),
                    p.fragment,
                )
            )
        except Exception:  # noqa: BLE001
            pass
    return cand, note


def _request(url: str, ctx) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        return {"status": resp.status, "final_url": resp.geturl(), "note": ""}


def check_one(url: str) -> dict:
    """请求单个 URL，返回状态信息。证书错误时降级重试一次。"""
    try:
        return _request(url, ssl.create_default_context())
    except urllib.error.HTTPError as e:
        return {"status": e.code, "final_url": e.geturl(), "note": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        reason = getattr(e, "reason", e)
        is_ssl = isinstance(reason, ssl.SSLError) or isinstance(e, ssl.SSLError)
        if is_ssl:
            try:
                r = _request(url, ssl._create_unverified_context())
                r["note"] = "可访问但证书异常"
                return r
            except Exception as e2:  # noqa: BLE001
                reason2 = getattr(e2, "reason", e2)
                return {"status": "", "final_url": "", "note": f"证书/连接错误：{type(reason2).__name__}"}
        return {"status": "", "final_url": "", "note": f"无法访问：{type(reason).__name__}"}


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        contests = crud.list_contests(db)
    finally:
        db.close()

    # (id, name, kind, 原始字段, 待检测URL或None, 预处理说明)
    tasks = []
    for c in contests:
        for kind, raw in (("官方通知", c.notice_url), ("报名入口", c.registration_url)):
            if not raw:
                continue
            url, prep_note = normalize_url(raw)
            tasks.append((c.id, c.name, kind, raw, url, prep_note))

    checkable = [t for t in tasks if t[4]]
    print(f"共 {len(contests)} 条竞赛，链接字段 {len(tasks)} 个，其中有效 URL {len(checkable)} 个，并发检测中……")
    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {}
        for cid, name, kind, raw, url, prep_note in checkable:
            future_map[pool.submit(check_one, url)] = (cid, kind)
        for fut in as_completed(future_map):
            cid, kind = future_map[fut]
            try:
                results[(cid, kind)] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[(cid, kind)] = {"status": "", "final_url": "", "note": f"检测异常：{e}"}
            print(f"  [{cid} {kind}] {results[(cid, kind)]['note'] or results[(cid, kind)]['status']}")

    rows = []
    for cid, name, kind, raw, url, prep_note in tasks:
        if url is None:
            r = {"status": "", "final_url": "", "note": prep_note}
            auto = "非链接内容（需改为空并在备注说明）"
        else:
            r = results.get((cid, kind), {"status": "", "final_url": "", "note": "未检测"})
            note = "；".join(x for x in (prep_note, r["note"]) if x)
            r["note"] = note
            if r["status"] == 200:
                auto = "可访问（待人工确认页面内容）"
            elif r["status"] != "":
                auto = "无法访问（HTTP错误）"
            else:
                auto = "无法访问"
        rows.append(
            {
                "竞赛ID": cid,
                "竞赛名称": name,
                "链接类型": kind,
                "链接地址(原始字段)": raw,
                "HTTP状态码": r["status"],
                "自动检测结果": auto,
                "检测备注": r["note"],
                "跳转后地址": r["final_url"],
                "人工复核结论(可用/失效/待确认)": "",
                "复核人": "",
                "复核日期": "",
            }
        )

    with open(REPORT, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(1 for r in rows if r["自动检测结果"].startswith("可访问"))
    bad = sum(1 for r in rows if r["自动检测结果"].startswith("无法访问"))
    text = sum(1 for r in rows if r["自动检测结果"].startswith("非链接"))
    print(f"\n检测完成：可访问 {ok} 个，无法访问 {bad} 个，非链接内容 {text} 个")
    print(f"报告已生成：{REPORT}")
    print("下一步：把报告发给田淋元/文博卉人工复核，确认后回填结论列，再由陈玉婷批量更新数据库 link_status。")


if __name__ == "__main__":
    main()
