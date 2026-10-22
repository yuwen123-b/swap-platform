-- 迁移脚本：位置公开开关（2026-10-12）
-- 背景：原先用 latitude/longitude 是否为 NULL 判断「位置是否公开」，与「离我最近」
--       功能语义冲突（想用附近搜索但不想公开位置时无法表达）。
--       改为独立字段 location_public 承载隐私语义，与位置是否存在解耦。
-- 说明：本脚本与 app/db/pool.py 的 ensure_location_columns() 等价，可手工执行；
--       后端启动时也会幂等执行相同变更，重复执行不会报错。

-- user 表：位置是否公开（0=不公开，1=公开），默认 0（新增用户默认不公开）
ALTER TABLE `user` ADD COLUMN `location_public` TINYINT NOT NULL DEFAULT 0
  COMMENT '位置是否公开：0不公开 1公开';
