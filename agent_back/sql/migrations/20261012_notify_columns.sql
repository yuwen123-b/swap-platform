-- ============================================================
-- 通知设置三列（个人中心 /profile/notifications）
-- 状态：**仅留档**，本目录不会被自动执行（initialize_schema 只扫 sql/*.sql，
--       而 ALTER TABLE 非幂等，放进 sql/ 会导致第二次启动 Duplicate column 报错）。
-- 实际生效路径：app/db/pool.py 的 ensure_notification_columns()，
--       由 app/main.py 的 startup() 调用，内部用 information_schema 判存在后再执行。
-- 手动执行（可选）：
--   mysql -u<user> -p <db> < sql/migrations/20261012_notify_columns.sql
-- ============================================================
ALTER TABLE `user` ADD COLUMN `notify_message` TINYINT NOT NULL DEFAULT 1 COMMENT '私信通知：0关 1开';
ALTER TABLE `user` ADD COLUMN `notify_exchange` TINYINT NOT NULL DEFAULT 1 COMMENT '交换状态通知：0关 1开';
ALTER TABLE `user` ADD COLUMN `notify_system` TINYINT NOT NULL DEFAULT 1 COMMENT '系统公告：0关 1开';
