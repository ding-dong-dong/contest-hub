#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Crawl one allow-listed 4C official notice into a review-only JSON candidate.

This script never writes contests.db and never calls the public write API. Its output
must be reviewed before another process imports it into production data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

ALLOWED_HOSTS = {"jsjds.blcu.edu.cn"}
DEFAULT_URL = "https://jsjds.blcu.edu.cn/info/1042/2294.htm"
USER_AGENT = "ContestHubReviewCrawler/0.1 (+https://gitee.com/chenyuting0510/contest-hub)"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CrawlError(RuntimeError):
    """A safe, user-facing crawl failure."""


class VisibleTextParser(HTMLParser):
    """Extract visible text without preserving the source page markup."""

    ignored_tags = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.ignored_tags:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        value = normalize_text(data)
        if not value:
            return
        self.text_parts.append(value)
        if self._in_title:
            self.title_parts.append(value)


@dataclass(frozen=True)
class ParsedPage:
    title: str
    text: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def parse_page(html: str) -> ParsedPage:
    parser = VisibleTextParser()
    parser.feed(html)
    return ParsedPage(
        title=normalize_text(" ".join(parser.title_parts)),
        text=normalize_text(" ".join(parser.text_parts)),
    )


def ensure_allowed_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise CrawlError("只允许抓取 HTTPS 官方页面")
    if parsed.hostname not in ALLOWED_HOSTS:
        raise CrawlError(f"域名不在白名单：{parsed.hostname or '空'}")
    if parsed.username or parsed.password:
        raise CrawlError("URL 不得包含账号信息")


def fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    ensure_allowed_url(url)
    robots_url = urljoin(url, "/robots.txt")
    robots = RobotFileParser(robots_url)
    robots.set_url(robots_url)
    try:
        robots.read()
    except OSError as exc:
        raise CrawlError(f"无法读取 robots.txt，按禁止抓取处理：{exc}") from exc
    if not robots.can_fetch(USER_AGENT, url):
        raise CrawlError("robots.txt 不允许抓取该页面")

    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            ensure_allowed_url(response.geturl())
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise CrawlError(f"目标不是 HTML 页面：{content_type}")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise CrawlError("页面超过 2 MiB 安全上限")
            charset = response.headers.get_content_charset() or "utf-8"
    except CrawlError:
        raise
    except OSError as exc:
        raise CrawlError(f"官网请求失败：{exc}") from exc
    try:
        return body.decode(charset), charset
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace"), "utf-8-replace"


def _extract_session(text: str) -> str:
    match = re.search(r"(20\d{2})\s*年\s*[（(]\s*第\s*(\d+)\s*届\s*[）)]", text)
    return f"第{match.group(2)}届·{match.group(1)}" if match else ""


def _extract_eligibility(text: str) -> str:
    match = re.search(r"参赛对象为([^。；]{8,180})", text)
    return normalize_text("参赛对象为" + match.group(1)) if match else "待确认"


def _extract_categories(text: str) -> list[str]:
    block = re.search(r"大赛分设\s*\d+\s*个大类，分别是(.{20,700}?)(?:详见|大赛国赛|。)", text)
    if not block:
        return []
    values = re.findall(r"[（(]\s*\d+\s*[）)]\s*([^；;。]+)", block.group(1))
    return [normalize_text(value) for value in values if normalize_text(value)]


def extract_candidate(
    html: str,
    source_url: str = DEFAULT_URL,
    competition_id: str = "imp_015",
    fetched_at: datetime | None = None,
) -> dict:
    """Extract only facts supported by the official page; editorial fields stay empty."""
    ensure_allowed_url(source_url)
    page = parse_page(html)
    text = page.text
    if "中国大学生计算机设计大赛" not in text:
        raise CrawlError("页面内容不像中国大学生计算机设计大赛官方通知")

    fetched_at = fetched_at or datetime.now(timezone.utc)
    session = _extract_session(text)
    eligibility = _extract_eligibility(text)
    categories = _extract_categories(text)
    organizer = (
        "中国大学生计算机设计大赛组织委员会"
        if "中国大学生计算机设计大赛组织委员会" in text
        else ""
    )
    warnings = [
        "报名截止时间未从总通知中可靠提取，需人工查阅校赛或省赛通知",
        "推荐专业及推荐依据属于编辑判断，爬虫不自动生成",
        "报名入口、材料和流程需人工复核",
        "官方总通知未明确专业限制，major_limit 保持待确认",
    ]
    if not session:
        warnings.append("届次未识别")
    if eligibility == "待确认":
        warnings.append("参赛对象未识别")

    return {
        "crawl_meta": {
            "parser": "official_4c_v1",
            "source_url": source_url,
            "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
            "content_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "review_status": "待审核",
            "auto_publish": False,
            "warnings": warnings,
        },
        "contest": {
            "id": competition_id,
            "name": "中国大学生计算机设计大赛（4C）",
            "session": session,
            "category": "综合",
            "tags": categories,
            "organizer": organizer,
            "eligible_grades": ["大一", "大二", "大三", "大四"]
            if "本科生" in eligibility
            else [],
            "major_limit": "待确认",
            "recommended_majors": [],
            "recommended_major_reason": None,
            "school_limit": "全国普通高校" if "全国" in eligibility else "待确认",
            "registration_deadline": "",
            "registration_deadline_note": "需以校赛或省赛通知为准",
            "submission_deadline": "",
            "submission_deadline_note": "待人工核对各类别通知",
            "materials": "",
            "process": "",
            "skills": "",
            "ability_training": "",
            "outcomes": "",
            "estimated_time": "",
            "notice_url": source_url,
            "registration_url": "",
            "source_type": "官网",
            "verified_at": fetched_at.date().isoformat(),
            "status": "待确认",
            "link_status": {"notice": "可用", "registration": "待确认"},
            "review_note": "爬虫候选记录；人工审核通过前不得发布",
        },
        "evidence": {
            "page_title": page.title,
            "session": session or None,
            "eligibility": None if eligibility == "待确认" else eligibility,
            "categories": categories,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 4C 官网通知并生成待审核候选 JSON")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--competition-id", default="imp_015")
    parser.add_argument("--output", default="staging/crawler/imp_015.json")
    parser.add_argument("--html-file", help="使用本地 HTML 调试；不会访问网络")
    args = parser.parse_args()

    if args.html_file:
        html = Path(args.html_file).read_text(encoding="utf-8")
    else:
        html, _charset = fetch_html(args.url)
    candidate = extract_candidate(html, args.url, args.competition_id)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已生成待审核候选：{output}")
    print("未写入数据库，未自动发布。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
