# 前端数据与官网爬虫候选契约

## 前端公开展示需要的数据

前端消费 `ContestOut`，字段分为四组：

1. 身份与分类：`id`、`name`、`session`、`category`、`tags`、`organizer`。
2. 资格与时间：`eligible_grades`、`major_limit`、`school_limit`、报名/作品截止时间及说明、`status`。
3. 价值与推荐：`skills`、`ability_training`、`outcomes`、`estimated_time`、
   `recommended_majors`、`recommended_major_reason`。
4. 来源与复核：`notice_url`、`registration_url`、`source_type`、`verified_at`、
   `link_status`、`review_note`。

`major_limit` 是官方资格原文；`recommended_majors` 是团队基于赛道、任务、材料或评审标准作出的
编辑判断。两者不得互相替代。

## 爬虫负责什么

爬虫只从白名单官网提取能够直接举证的事实，并输出 JSON 候选：

- 官网地址、页面标题、抓取时间、内容 SHA-256；
- 届次、主办方、参赛对象、官方列出的赛道；
- 能够明确定位的日期和入口；
- 自动提取失败或含义不明确的字段保持空值或“待确认”。

“参赛对象”只能支持年级和院校资格，不能在官网没有明确表述时推断为专业限制。

爬虫不得自动生成推荐专业、价值判断、能力训练说明或学校学分认定，也不得写入正式数据库。

## 人工审核负责什么

审核人需要补齐并确认：

- 报名截止与作品截止是否属于当前届次；
- 专业限制、年级和院校资格；
- 推荐专业及 30–150 字推荐依据；
- 能力、成果、投入时间和报名入口；
- 引用是否为必要的短事实，是否含个人信息；
- 来源链接是否可用，竞赛状态是否准确。

只有审核状态变为“可录入”的候选才能进入导入流程。

## 当前原型

运行：

```powershell
python scripts/crawl_official_4c.py
```

默认读取 4C 2026 官方通知，输出到 `staging/crawler/imp_015.json`。该目录只保存候选数据，
不代表数据已经审核或发布。使用 `--html-file` 可以对本地 HTML 做离线解析测试。

安全边界：

- 仅允许 HTTPS 和 `jsjds.blcu.edu.cn` 白名单域名；
- 每次联网前检查 `robots.txt`；读取失败时停止；
- 单页最大 2 MiB，默认超时 20 秒；
- 不执行登录、验证码、反爬绕过或批量并发；
- 输出固定为“待审核”和 `auto_publish=false`。
