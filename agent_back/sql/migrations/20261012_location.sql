-- 迁移脚本：智能体助手「附近物品查询」地理位置列（2026-10-12）
-- 说明：本脚本与 app/db/pool.py 的 ensure_location_columns() 等价，可手工执行；
-- 后端启动时也会幂等执行相同变更，重复执行不会报错。
-- 注意：MySQL 8.0 不支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，
-- 手工执行前请先确认列不存在，或交由后端启动时幂等迁移。

-- 一、user 表：用户常驻位置（由个人中心设置）
ALTER TABLE `user` ADD COLUMN `latitude` DECIMAL(10,7) NULL COMMENT '用户纬度（个人中心设置）';
ALTER TABLE `user` ADD COLUMN `longitude` DECIMAL(10,7) NULL COMMENT '用户经度（个人中心设置）';
ALTER TABLE `user` ADD COLUMN `community` VARCHAR(64) NULL COMMENT '所在小区/社区名称';

-- 二、item 表：物品所在位置（发布时填写，供 find_nearby_items 做 Haversine 距离排序）
ALTER TABLE `item` ADD COLUMN `latitude` DECIMAL(10,7) NULL COMMENT '物品纬度';
ALTER TABLE `item` ADD COLUMN `longitude` DECIMAL(10,7) NULL COMMENT '物品经度';
