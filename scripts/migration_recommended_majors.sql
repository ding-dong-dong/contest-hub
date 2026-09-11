-- 推荐专业 V1.0 数据库迁移脚本（陈玉婷，2026-09-11）
-- 依据：田淋元《推荐专业规则与验收清单 V1.0》
-- 说明：
--   1. 应用启动时 app/database.py 的 _run_migrations() 会自动执行等价 ALTER（无需手工跑）；
--   2. 本脚本供手工/其他环境迁移与审计使用，SQLite 3.35+ 支持 DROP COLUMN；
--   3. 重复执行安全：列已存在时跳过（SQLite 没有 ADD COLUMN IF NOT EXISTS，见下方说明）。

-- recommended_majors：10 枚举 JSON 数组字符串；旧数据缺省为 '[]'（空数组，不是 null）
ALTER TABLE contests ADD COLUMN recommended_majors TEXT DEFAULT '[]';

-- recommended_major_reason：30-150 字推荐依据；旧数据/无依据为 NULL
ALTER TABLE contests ADD COLUMN recommended_major_reason TEXT;

-- 迁移后校验（应输出 30 / 0）：
-- SELECT COUNT(*) FROM contests;                                   -- 30
-- SELECT COUNT(*) FROM contests WHERE recommended_majors IS NULL;  -- 0
