import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "crawl_official_4c.py"
SPEC = importlib.util.spec_from_file_location("crawl_official_4c", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


SAMPLE_HTML = """
<!doctype html>
<html lang="zh-CN">
  <head><title>4C2026通知-中国大学生计算机设计大赛</title></head>
  <body>
    <h1>关于举办“2026年（第19届）中国大学生计算机设计大赛”的通知</h1>
    <p>2026年（第19届）中国大学生计算机设计大赛是由相关高校教师组成的
       中国大学生计算机设计大赛组织委员会主办，参赛对象为全国普通高校2026年
       在籍的本科生（含港澳台学生，以及来华留学生）。</p>
    <p>2026年大赛分设3个大类，分别是（1）软件应用与开发；（2）人工智能应用；
       （3）信息可视化设计。详见附件。</p>
    <script>参赛对象为不应被读取的脚本文本</script>
  </body>
</html>
"""


class OfficialCrawlerTests(unittest.TestCase):
    def test_extracts_supported_facts_and_keeps_editorial_fields_empty(self):
        candidate = MODULE.extract_candidate(
            SAMPLE_HTML,
            fetched_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        )
        contest = candidate["contest"]
        self.assertEqual(contest["id"], "imp_015")
        self.assertEqual(contest["session"], "第19届·2026")
        self.assertEqual(contest["organizer"], "中国大学生计算机设计大赛组织委员会")
        self.assertEqual(contest["eligible_grades"], ["大一", "大二", "大三", "大四"])
        self.assertEqual(contest["major_limit"], "待确认")
        self.assertIn("全国普通高校2026年", candidate["evidence"]["eligibility"])
        self.assertEqual(
            contest["tags"], ["软件应用与开发", "人工智能应用", "信息可视化设计"]
        )
        self.assertEqual(contest["recommended_majors"], [])
        self.assertIsNone(contest["recommended_major_reason"])
        self.assertEqual(candidate["crawl_meta"]["review_status"], "待审核")
        self.assertFalse(candidate["crawl_meta"]["auto_publish"])

    def test_rejects_unapproved_hosts_and_plain_http(self):
        with self.assertRaises(MODULE.CrawlError):
            MODULE.ensure_allowed_url("https://example.com/notice")
        with self.assertRaises(MODULE.CrawlError):
            MODULE.ensure_allowed_url("http://jsjds.blcu.edu.cn/notice")

    def test_rejects_unrelated_page(self):
        with self.assertRaises(MODULE.CrawlError):
            MODULE.extract_candidate("<html><body>普通页面</body></html>")


if __name__ == "__main__":
    unittest.main()
