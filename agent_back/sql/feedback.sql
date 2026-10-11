CREATE TABLE IF NOT EXISTS `platform_feedback` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id` BIGINT NOT NULL COMMENT '评价人ID',
  `rating` TINYINT NOT NULL COMMENT '评分：1~5',
  `content` VARCHAR(500) NOT NULL COMMENT '对程序的评价内容',
  `sentiment` VARCHAR(10) NOT NULL DEFAULT 'neutral' COMMENT '情感：positive=良好 neutral=中性 negative=差',
  `sentiment_score` FLOAT DEFAULT 0 COMMENT '情感分值 -1~1',
  `sentiment_engine` VARCHAR(10) DEFAULT 'lexicon' COMMENT '判定引擎：llm/lexicon',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_sentiment` (`sentiment`),
  KEY `idx_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='程序平台评价表'
