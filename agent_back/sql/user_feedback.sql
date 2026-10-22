-- 用户意见反馈表（个人中心 /profile/feedback 提交）
-- 说明：与程序评价表 platform_feedback（sql/feedback.sql，含 rating + 情感分析）语义不同，
--       故独立建表，互不影响。
-- 注意：sql/*.sql 由 initialize_schema() 在每次启动时全量执行，
--       本文件必须是**单条语句**（initialize_schema 使用单次 cursor.execute）。
--       CREATE TABLE IF NOT EXISTS 幂等，可安全重复执行。
CREATE TABLE IF NOT EXISTS `user_feedback` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id` BIGINT NOT NULL COMMENT '提交人用户ID',
  `content` TEXT NOT NULL COMMENT '反馈内容',
  `contact` VARCHAR(100) NULL COMMENT '联系方式（选填）',
  `status` TINYINT NOT NULL DEFAULT 0 COMMENT '处理状态：0待处理 1已处理',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_user_created` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户意见反馈表';
