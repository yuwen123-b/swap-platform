CREATE TABLE IF NOT EXISTS `ai_log` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `api_name` VARCHAR(64) NOT NULL COMMENT 'AI接口名称',
  `request_body` TEXT COMMENT '请求内容',
  `response_body` TEXT COMMENT '响应内容',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1=成功 0=失败',
  `duration_ms` INT DEFAULT NULL COMMENT '耗时毫秒',
  `error_msg` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_status` (`status`),
  KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI调用日志表'
