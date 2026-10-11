-- 迁移脚本：无障碍模式 + 国际化 + 360° 物品查看（2026-10-11）
-- 说明：本脚本与 app/db/pool.py 的 ensure_accessibility_columns() 等价，
-- 可手工执行；后端启动时也会幂等执行相同变更，重复执行不会报错（请使用 IF NOT EXISTS 版本前先确认列不存在）。
-- 注意：MySQL 8.0 不支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，
-- 手工执行前请先确认列不存在，或交由后端启动时幂等迁移。

-- 一、user 表：无障碍模式与语言偏好
ALTER TABLE `user` ADD COLUMN `mobility_level` VARCHAR(20) NOT NULL DEFAULT 'free' COMMENT '行动能力：free/limited/assisted';
ALTER TABLE `user` ADD COLUMN `accessibility_mode` VARCHAR(30) NOT NULL DEFAULT 'normal' COMMENT '无障碍模式：normal/visually_impaired/mobility_impaired';
ALTER TABLE `user` ADD COLUMN `preferred_lang` VARCHAR(10) NOT NULL DEFAULT 'zh_CN' COMMENT '界面语言：zh_CN/en_US';

-- 二、item 表：360° 四视角
ALTER TABLE `item` ADD COLUMN `panorama_views` TEXT NULL COMMENT '360° 四视角图路径（JSON）';
ALTER TABLE `item` ADD COLUMN `panorama_status` VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT 'none/generating/ready/failed';

-- 三、volunteer_task 表：志愿者代取任务
CREATE TABLE IF NOT EXISTS `volunteer_task` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `exchange_id` VARCHAR(64) NOT NULL COMMENT '关联的交换单号',
    `requester_id` BIGINT NOT NULL COMMENT '委托人用户ID',
    `volunteer_id` BIGINT NULL COMMENT '接单志愿者用户ID',
    `item_id` BIGINT NULL COMMENT '代取物品ID',
    `handover_method` VARCHAR(30) NOT NULL DEFAULT 'volunteer_pickup' COMMENT '交接方式',
    `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/accepted/done/cancelled',
    `note` VARCHAR(255) NULL COMMENT '备注',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_requester` (`requester_id`),
    KEY `idx_volunteer` (`volunteer_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
