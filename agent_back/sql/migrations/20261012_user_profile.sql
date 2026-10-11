-- 迁移脚本：个人中心持久化设置（2026-10-12）
-- 说明：本脚本与 app/db/pool.py 的 ensure_accessibility_columns() 等价，可手工执行；
-- 后端启动时也会幂等执行相同变更。
-- 注意：MySQL 8.0 不支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，
-- 手工执行前请先确认列不存在，或交由后端启动时幂等迁移。

-- user 表新增：助老模式开关、高对比度开关
-- （accessibility_mode / mobility_level / preferred_lang 见 20261011_accessibility_panorama.sql）
ALTER TABLE `user` ADD COLUMN `elderly_mode` TINYINT NOT NULL DEFAULT 0 COMMENT '助老模式开关：0关 1开';
ALTER TABLE `user` ADD COLUMN `high_contrast` TINYINT NOT NULL DEFAULT 0 COMMENT '高对比度开关：0关 1开';
