CREATE TABLE IF NOT EXISTS `report` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `reporter_id` BIGINT NOT NULL COMMENT '举报人用户ID',
  `target_type` TINYINT NOT NULL COMMENT '对象类型：1=物品 2=帖子 3=用户',
  `target_id` BIGINT NOT NULL COMMENT '被举报对象ID',
  `reason` VARCHAR(255) NOT NULL COMMENT '举报理由',
  `status` TINYINT NOT NULL DEFAULT 0 COMMENT '状态：0=待处理 1=已处理 2=已驳回',
  `handler_id` BIGINT DEFAULT NULL COMMENT '处理人管理员ID',
  `handle_time` DATETIME DEFAULT NULL COMMENT '处理时间',
  `result` VARCHAR(255) DEFAULT NULL COMMENT '处理结果说明',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`),
  KEY `idx_target` (`target_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='举报表'
