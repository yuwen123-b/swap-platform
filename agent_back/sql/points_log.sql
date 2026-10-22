-- 状态：本表目前仅建表，未接入业务写入
-- 后续接入需要实现四类流水：
--   1. 发布物品奖励（source=1）
--   2. 完成交换奖励（source=2）
--   3. 收到好评奖励（source=3）
--   4. 兑换消耗（source=5）
-- 字段说明：
--   balance 为冗余字段，写入时必须与 user.points 保持一致
--   related_id 存放关联的业务ID（如物品ID、交换ID）

-- ============================================================
-- 积分流水表（points_log）
-- 用途：记录用户积分变动明细，支撑个人中心「积分明细」列表。
-- 说明：user.points 为余额快照，本表为变动明细；两者由业务代码同步维护。
--       幂等可重复执行（IF NOT EXISTS）。
-- 唯一索引：uk_points_log_source(source, related_id, user_id) 为业务幂等键，
--   保证同一笔业务（同一 source + 同一 related_id）对同一用户只写一条流水。
--   已有库由 app/db/pool.py 的 ensure_points_log_unique_index() 幂等补建。
--   注意：MySQL 唯一索引不约束 NULL，source=4（管理员调整）约定 related_id 写 NULL，
--   因此管理员可对同一用户反复调整；发布奖励(1)/交换奖励(2) 必须带业务ID。
-- ============================================================

CREATE TABLE IF NOT EXISTS `points_log` (
  `id`           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`      BIGINT       NOT NULL COMMENT '用户ID',
  `points`       INT          NOT NULL COMMENT '积分变动值：正数为获得，负数为消耗',
  `balance`      INT          NOT NULL DEFAULT 0 COMMENT '变动后余额快照，便于对账',
  `source`       TINYINT      NOT NULL COMMENT '来源：1=发布物品 2=完成交换 3=收到好评 4=管理员调整 5=兑换消耗 6=免费送出奖励',
  `related_id`   BIGINT       DEFAULT NULL COMMENT '关联业务ID（物品/订单/评价等）；管理员调整写 NULL',
  `description`  VARCHAR(255) DEFAULT NULL COMMENT '变动说明，展示于明细列表',
  `created_at`   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_points_log_source` (`source`, `related_id`, `user_id`),
  KEY `idx_user_created` (`user_id`, `created_at`),
  KEY `idx_source` (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='积分变动流水表';
