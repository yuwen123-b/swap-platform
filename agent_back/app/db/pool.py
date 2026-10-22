import logging
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from dbutils.pooled_db import PooledDB
import pymysql
from app.core.config import settings

logger = logging.getLogger(__name__)


SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

@lru_cache
def get_pool() -> PooledDB:
    # 连接参数集中组装：本地 MySQL 与云数据库（Aiven 等）共用同一入口
    kwargs = dict(
        creator=pymysql,
        maxconnections=settings.db_pool_max_connections,
        mincached=settings.db_pool_min_cached,
        maxcached=settings.db_pool_max_cached,
        blocking=True,
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset=settings.db_charset,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=settings.db_connect_timeout,
    )
    if settings.db_ssl:
        if settings.db_ssl_ca:
            # 提供 CA 证书：双向校验（加密 + 服务端身份验证），Aiven 推荐级别
            kwargs["ssl"] = {"ca": settings.db_ssl_ca, "check_hostname": True}
        else:
            # 只加密不校验证书（等效 ssl_mode=REQUIRED）：
            # pymysql 的 ssl dict 只要有键即启用 TLS；check_hostname=False 免去无 CA 时的报错
            kwargs["ssl"] = {"check_hostname": False}
        logger.info("数据库 SSL 已启用（ca=%s）", settings.db_ssl_ca or "未提供，仅加密")
    return PooledDB(**kwargs)


@contextmanager
def connection():
    conn = get_pool().connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_schema() -> None:
    with connection() as conn:
        with conn.cursor() as cursor:
            for sql_file in sorted(SQL_DIR.glob("*.sql")):
                cursor.execute(sql_file.read_text(encoding="utf-8"))


def ensure_item_contact_column() -> None:
    """幂等迁移：item 表缺 contact 列时补齐（用户上传物品的联系方式）。"""
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'item' AND COLUMN_NAME = 'contact'"
            )
            if cursor.fetchone()["c"] == 0:
                cursor.execute(
                    "ALTER TABLE item ADD COLUMN contact VARCHAR(100) NULL COMMENT '联系方式'"
                )


def _ensure_column(cursor, table: str, column: str, ddl: str) -> None:
    """幂等加列：information_schema 判断列是否存在，不存在才执行 ddl。"""
    cursor.execute(
        "SELECT COUNT(*) AS c FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
    )
    if cursor.fetchone()["c"] == 0:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _ensure_index(cursor, table: str, index: str, ddl: str) -> bool:
    """幂等建索引：information_schema.STATISTICS 判断索引是否存在，不存在才执行 ddl。

    与 _ensure_column 同思路——ALTER/CREATE INDEX 非幂等，重复执行会报
    Duplicate key name 直接让后端起不来，因此必须先做存在性判断。
    返回是否真正执行了 ddl（便于测试断言与日志）。
    """
    cursor.execute(
        "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s",
        (table, index),
    )
    if cursor.fetchone()["c"] == 0:
        cursor.execute(ddl)
        return True
    return False


def ensure_accessibility_columns() -> None:
    """幂等迁移：无障碍/国际化/360° 所需的表结构变更。

    - user：mobility_level、accessibility_mode、preferred_lang
    - item：panorama_views、panorama_status
    - volunteer_task：志愿者代取任务表
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            _ensure_column(cursor, "user", "mobility_level",
                           "mobility_level VARCHAR(20) NOT NULL DEFAULT 'free' COMMENT '行动能力：free/limited/assisted'")
            _ensure_column(cursor, "user", "accessibility_mode",
                           "accessibility_mode VARCHAR(30) NOT NULL DEFAULT 'normal' COMMENT '无障碍模式：normal/visually_impaired/mobility_impaired'")
            _ensure_column(cursor, "user", "preferred_lang",
                           "preferred_lang VARCHAR(10) NOT NULL DEFAULT 'zh_CN' COMMENT '界面语言：zh_CN/en_US'")
            _ensure_column(cursor, "user", "elderly_mode",
                           "elderly_mode TINYINT NOT NULL DEFAULT 0 COMMENT '助老模式开关：0关 1开'")
            _ensure_column(cursor, "user", "high_contrast",
                           "high_contrast TINYINT NOT NULL DEFAULT 0 COMMENT '高对比度开关：0关 1开'")
            _ensure_column(cursor, "item", "panorama_views",
                           "panorama_views TEXT NULL COMMENT '360° 四视角图路径（JSON）'")
            _ensure_column(cursor, "item", "panorama_status",
                           "panorama_status VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT 'none/generating/ready/failed'")
            _ensure_column(cursor, "item", "panorama_generated_at",
                           "panorama_generated_at DATETIME NULL COMMENT '360° 生成完成时间'")
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS `volunteer_task` (
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
                   ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"""
            )


def ensure_model_columns() -> None:
    """幂等迁移：item 表 3D 模型相关三列（百炼 Tripo 图生 3D）。

    - model_url：GLB 静态地址 `/api/v1/static/items/{id}/models/model.glb`。
      与 panorama_views 同口径——**不存签名**，签名在读取时现场补
      （签名带 1 小时有效期，落库会立刻过期）。
    - model_status：none / generating / ready / failed，未生成过为 none。
    - model_generated_at：置 generating 时写起始时间，供 get_model 做「卡死超时」兜底。
      3D 任务生成 2~4 分钟（比 360° 更久），没有这一列后端一重启，
      前端就会永久转圈，因此比 panorama 更必要。
    - model_error：最近一次失败的**原因原文**（成功/生成中时置 NULL）。
      没有这一列时，失败只剩终端里一行 logger.warning，前端只看到「failed」三个字母，
      用户视角就是「点了没反应」——2026-10-16 排查「3D 按钮无反应」时，
      真实原因（百炼 `The product is not activated`）在库里、在接口里都查不到，
      只能靠另写脚本重放请求才拿到。落库 + 透出后，同类问题一次点击即可定位。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            _ensure_column(cursor, "item", "model_url",
                           "model_url VARCHAR(500) NULL COMMENT '3D 模型（GLB）静态地址（不带签名）'")
            _ensure_column(cursor, "item", "model_status",
                           "model_status VARCHAR(16) NOT NULL DEFAULT 'none' COMMENT 'none/generating/ready/failed'")
            _ensure_column(cursor, "item", "model_generated_at",
                           "model_generated_at DATETIME NULL COMMENT '3D 模型生成完成时间'")
            _ensure_column(cursor, "item", "model_error",
                           "model_error VARCHAR(500) NULL COMMENT '最近一次 3D 生成失败原因（成功/生成中清空）'")


def ensure_location_columns() -> None:
    """幂等迁移：为智能体助手「附近物品查询」功能补齐地理位置列。

    - user：latitude / longitude / community（用户常驻位置，由个人中心设置）
            location_public（位置是否公开，与位置存在与否解耦）
    - item：latitude / longitude（物品所在位置，发布时填写）
    列存在则跳过；新增列默认 NULL，不影响现有数据。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            _ensure_column(cursor, "user", "latitude",
                           "latitude DECIMAL(10,7) NULL COMMENT '用户纬度（个人中心设置）'")
            _ensure_column(cursor, "user", "longitude",
                           "longitude DECIMAL(10,7) NULL COMMENT '用户经度（个人中心设置）'")
            _ensure_column(cursor, "user", "community",
                           "community VARCHAR(64) NULL COMMENT '所在小区/社区名称'")
            # 楼栋：位置管理页展示与「手动输入地址」写入。真实表中通常已存在，
            # 这里做幂等兜底，避免 _PROFILE_COLUMNS 因缺列导致 /user/profile 整体 500。
            _ensure_column(cursor, "user", "building",
                           "building VARCHAR(64) NULL COMMENT '楼栋/单元信息'")
            # 位置公开开关：默认 0（不公开），需用户显式开启后才出现在他人附近搜索结果中
            _ensure_column(cursor, "user", "location_public",
                           "location_public TINYINT NOT NULL DEFAULT 0 COMMENT '位置是否公开：0不公开 1公开'")
            _ensure_column(cursor, "item", "latitude",
                           "latitude DECIMAL(10,7) NULL COMMENT '物品纬度'")
            _ensure_column(cursor, "item", "longitude",
                           "longitude DECIMAL(10,7) NULL COMMENT '物品经度'")


def ensure_notification_columns() -> None:
    """幂等迁移：用户通知偏好三列，默认全部开启（1）。

    注意：ALTER TABLE 非幂等，不能放进 sql/*.sql（initialize_schema 每次启动全量执行，
    第二次启动会因 Duplicate column 直接启动失败），必须走 _ensure_column 判断。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            _ensure_column(cursor, "user", "notify_message",
                           "notify_message TINYINT NOT NULL DEFAULT 1 COMMENT '私信通知：0关 1开'")
            _ensure_column(cursor, "user", "notify_exchange",
                           "notify_exchange TINYINT NOT NULL DEFAULT 1 COMMENT '交换状态通知：0关 1开'")
            _ensure_column(cursor, "user", "notify_system",
                           "notify_system TINYINT NOT NULL DEFAULT 1 COMMENT '系统公告：0关 1开'")


# 积分/碳减排规则的默认值：(config_key, config_value, description)
# 键名与 app/services/points_service.py 的 RULE_* 常量、admin/points.py 的 RULE_KEYS 对齐；
# 数值与 points_service 的 DEFAULT_* 常量同值——这里不 import services 层，
# 避免 db 层反向依赖业务层。
_DEFAULT_POINTS_RULES = (
    ("points_publish", "20", "发布物品奖励积分"),
    ("points_exchange", "50", "完成交换奖励积分"),
    ("carbon_per_exchange", "5.0", "每次完成交换折算的碳减排量(kgCO2e)"),
)


def ensure_points_rules() -> None:
    """幂等写入积分规则默认值。

    用 INSERT IGNORE：仅在键不存在时插入，**绝不覆盖管理员已配置的值**。

    为什么不放 sql/*.sql：
    1. initialize_schema 对每个文件只做一次 execute，单文件只能写一条语句；
    2. 它没有 try/except，sys_config 若不存在会直接导致后端启动失败；
       这里捕获异常后只记录警告，积分读取侧另有代码内默认值兜底，不阻断启动。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                placeholders = ", ".join(["(%s, %s, %s)"] * len(_DEFAULT_POINTS_RULES))
                params = [value for row in _DEFAULT_POINTS_RULES for value in row]
                cursor.execute(
                    f"INSERT IGNORE INTO sys_config (config_key, config_value, description) "
                    f"VALUES {placeholders}",
                    params,
                )
    except Exception:  # noqa: BLE001 — 初始化失败不应阻断服务启动
        logger.warning(
            "积分规则默认值写入失败（sys_config 不可用？），积分发放将依赖代码内默认值",
            exc_info=True,
        )


# 积分流水的业务幂等键名（与 sql/points_log.sql 的建表语句保持一致）
POINTS_LOG_UNIQUE_INDEX = "uk_points_log_source"


def ensure_points_log_columns() -> None:
    """幂等迁移：把 points_log 表结构对齐 sql/points_log.sql。

    为什么需要：线上这张表是**手工建的老版本**，CREATE TABLE IF NOT EXISTS 对已存在的表
    完全不起作用，于是长期与 schema 漂移，导致两类 500：
    1. 缺 `balance` 列 → `GET /user/carbon/logs` 的 SELECT 与 `award_points` 的 INSERT
       都报 1054 Unknown column 'balance' in 'field list'（积分明细页 500、发分全挂）；
    2. `description` 只有 VARCHAR(100)，而代码按 255 截断 → 管理员调整备注稍长即报
       1406 Data too long（`[管理员调整] ` 8 字符 + reason 最长 100 → 108 > 100）。

    ALTER TABLE 非幂等，不能放进 sql/*.sql（initialize_schema 每次启动全量执行且无
    try/except，第二次启动会直接让后端起不来），因此统一走这里做存在性判断。
    """
    with connection() as conn:
        with conn.cursor() as cursor:
            _ensure_column(
                cursor, "points_log", "balance",
                "balance INT NOT NULL DEFAULT 0 COMMENT '变动后余额快照，便于对账'",
            )
            cursor.execute(
                "SELECT COLUMN_TYPE AS t FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'points_log' "
                "AND COLUMN_NAME = 'description'"
            )
            row = cursor.fetchone()
            # 只在宽度确实不足时才 MODIFY，避免无意义的表重建
            if row and str(row.get("t") or "").lower() not in ("varchar(255)", ""):
                cursor.execute(
                    "ALTER TABLE points_log MODIFY COLUMN description VARCHAR(255) DEFAULT NULL "
                    "COMMENT '变动说明，展示于明细列表'"
                )
                logger.info("points_log.description 已扩展为 VARCHAR(255)")


def ensure_points_log_unique_index() -> None:
    """幂等迁移：为 points_log 建业务幂等唯一索引 (source, related_id, user_id)。

    为什么需要它：
    「审核通过发发布奖励」「交换完成发交换奖励」目前都靠应用层读旧状态做幂等
    （item.status != 4 直接 400、order.previous_status != 3 才发分）。并发下两个请求
    可能同时通过校验，唯一索引是数据库层的最后一道闸——同一笔业务绝不会重复写流水，
    从而保证 user.points 与 points_log 永远对得上。

    为什么 related_id 为 NULL 的记录不受约束：
    MySQL 唯一索引不约束 NULL，`NULL != NULL`。管理员调整积分（source=4）约定
    related_id 写 NULL，因此同一管理员可对同一用户反复加分/扣分，不会被本索引拦截。

    为什么走这里而不放进 sql/*.sql：
    initialize_schema 每次启动对每个文件全量执行且没有 try/except，而 ALTER TABLE
    非幂等——第二次启动会因 Duplicate key name 直接导致后端启动失败。

    存量脏数据（已有重复的 source+related_id+user_id）会让建索引失败：
    此时只记录 ERROR 并给出排查 SQL，不阻断服务启动。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS c FROM information_schema.STATISTICS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'points_log' AND INDEX_NAME = %s",
                    (POINTS_LOG_UNIQUE_INDEX,),
                )
                if cursor.fetchone()["c"]:
                    return

                # 建索引前必须先清掉会撞唯一键的历史哨兵值，否则 ALTER 必然 1062：
                #   - related_id=0：老数据/种子数据把「无关联」写成 0（真实业务ID 从 1 开始，
                #     0 不可能是合法业务ID），0 是确定值会被判重 → 统一改回约定值 NULL
                #     （MySQL 唯一索引不约束 NULL，NULL 行之间不冲突）；
                #   - source=4：管理员调整在旧代码里把 admin_id 写进 related_id（语义误用），
                #     同一管理员调同一用户多次就会重复 → 同样归 NULL，新代码已固定写 NULL。
                # 只改 related_id 一个字段，不删行、不动 points/user_id/description。
                cursor.execute("UPDATE points_log SET related_id=NULL WHERE related_id=0 OR source=4")
                if cursor.rowcount:
                    logger.info(
                        "points_log 存量哨兵值 related_id 已规范化为 NULL：%s 行（为建唯一索引做准备）",
                        cursor.rowcount,
                    )

                cursor.execute(
                    f"ALTER TABLE points_log ADD UNIQUE KEY {POINTS_LOG_UNIQUE_INDEX} "
                    "(source, related_id, user_id)"
                )
                logger.info("points_log 唯一索引 %s 创建完成", POINTS_LOG_UNIQUE_INDEX)
    except Exception:  # noqa: BLE001 — 存量重复行会导致建索引失败，不应阻断启动
        logger.error(
            "points_log 唯一索引 %s 创建失败（存量可能存在重复的 source+related_id+user_id）。"
            "请执行 SELECT source, related_id, user_id, COUNT(*) c FROM points_log "
            "GROUP BY source, related_id, user_id HAVING c > 1; 清理重复行后重启服务。",
            POINTS_LOG_UNIQUE_INDEX,
            exc_info=True,
        )


# 收藏表的幂等键名（业务语义：同一用户对同一物品只应有一条收藏）
FAVORITE_UNIQUE_INDEX = "uk_user_item"
# 收藏列表的排序键（按收藏时间倒序分页）
FAVORITE_USER_CREATED_INDEX = "idx_user_created"


def ensure_personal_center_tables() -> None:
    """幂等迁移：个人中心「我的收藏」所需的表与索引。

    为什么复用既有 `favorite` 而不是新建 `item_favorite`：
    真实库中 `favorite` 表已存在，列（id/user_id/item_id/created_at）与设计完全一致，
    只是缺唯一索引。再建一张同义表只会造成双份数据源与后续维护歧义。

    为什么必须补唯一索引：
    「收藏」是幂等操作，重复点击不得产生重复行。`uk_user_item (user_id, item_id)`
    是数据库层的最后一道闸（应用层同时用 INSERT IGNORE 兜底）；
    `idx_user_created (user_id, created_at)` 支撑「我的收藏」按时间倒序分页。

    为什么走这里而不放进 sql/*.sql：
    1. CREATE TABLE IF NOT EXISTS 对已存在的表无效，无法补索引；
    2. ALTER TABLE 非幂等，而 initialize_schema 每次启动全量执行且没有 try/except，
       第二次启动会因 Duplicate key name 直接导致后端启动失败。

    存量重复收藏会让唯一索引建不上：此时只记录 ERROR 并给出排查 SQL，不阻断启动。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `favorite` (
                           `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `user_id` BIGINT NOT NULL COMMENT '收藏人',
                           `item_id` BIGINT NOT NULL COMMENT '被收藏的物品',
                           `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '收藏时间',
                           PRIMARY KEY (`id`),
                           KEY `idx_user_id` (`user_id`),
                           KEY `idx_item_id` (`item_id`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物品收藏表'"""
                )
                if _ensure_index(
                    cursor, "favorite", FAVORITE_UNIQUE_INDEX,
                    f"ALTER TABLE `favorite` ADD UNIQUE KEY {FAVORITE_UNIQUE_INDEX} (user_id, item_id)",
                ):
                    logger.info("favorite 唯一索引 %s 创建完成", FAVORITE_UNIQUE_INDEX)
                if _ensure_index(
                    cursor, "favorite", FAVORITE_USER_CREATED_INDEX,
                    f"ALTER TABLE `favorite` ADD KEY {FAVORITE_USER_CREATED_INDEX} (user_id, created_at)",
                ):
                    logger.info("favorite 索引 %s 创建完成", FAVORITE_USER_CREATED_INDEX)
    except Exception:  # noqa: BLE001 — 存量重复收藏会导致建唯一索引失败，不应阻断启动
        logger.error(
            "favorite 表 / 索引初始化失败（存量可能存在重复的 user_id+item_id）。"
            "请执行 SELECT user_id, item_id, COUNT(*) c FROM favorite "
            "GROUP BY user_id, item_id HAVING c > 1; 清理重复行后重启服务。",
            exc_info=True,
        )


# 需求表（我想要的）索引名
DEMAND_USER_STATUS_INDEX = "idx_user_status"
DEMAND_STATUS_CREATED_INDEX = "idx_status_created"


# ============================================================
# 商家端闭环：用户赚积分 → 兑换商家服务 → 商家核销 → 平台结算
# ============================================================
MERCHANT_USER_UNIQUE_INDEX = "uk_merchant_user"
REDEMPTION_ORDER_NO_UNIQUE_INDEX = "uk_redemption_order_no"
REDEMPTION_CODE_UNIQUE_INDEX = "uk_redemption_code"

# 种子商家（模拟数据）。user_id 一律留 NULL —— 平台代录，
# 不绑定任何真实账号，避免与现有 12 个用户产生身份耦合。
_MERCHANT_SEED = (
    # (name, category, contact, address, description)
    ("社区打印店", "打印", "13800000001", "小区北门 1 号楼底商", "打印、复印、扫描、装订，支持微信发文件，扫码即取。"),
    ("24小时便利店", "便利店", "13800000002", "小区东门商业街 3 号", "24 小时营业，日用百货、零食饮料、代收快递。"),
    ("美发工作室", "理发", "13800000003", "小区西门 2 号楼 102", "社区老牌理发店，老人小孩剪发优先，可电话预约。"),
    ("绿源回收站", "回收", "13800000004", "小区南门外 200 米", "旧衣、旧家电、纸箱回收，可上门取件。"),
    ("家政服务站", "家政", "13800000005", "物业服务中心二楼", "保洁、家电清洗、钟点工服务，服务人员持证上岗。"),
)

# 种子商品 (merchant_name, title, description, points_cost, stock)
_MERCHANT_PRODUCT_SEED = (
    ("社区打印店", "打印券10张", "A4 黑白单面打印 10 张，不限时段使用。", 50, 100),
    ("社区打印店", "复印券20张", "A4 黑白复印 20 张，可代为扫描存档。", 80, 100),
    ("24小时便利店", "纸巾1包", "抽取式面巾纸 1 包（约 100 抽）。", 30, 200),
    ("24小时便利店", "洗衣液500ml", "500ml 手洗 / 机洗通用洗衣液一瓶。", 100, 60),
    ("美发工作室", "基础理发券", "成人基础剪发一次（含洗头吹干）。", 200, 50),
    ("美发工作室", "洗剪吹套餐", "洗发 + 剪发 + 吹造型一次。", 300, 30),
    ("绿源回收站", "旧衣回收抵扣券", "旧衣回收满 5kg 抵扣一次。", 50, 80),
    ("绿源回收站", "旧家电估价券", "免费上门评估旧家电回收价，不限件数。", 0, 999),
    ("家政服务站", "保洁1小时", "专业保洁上门服务 1 小时，仅限小区内。", 500, 20),
    ("家政服务站", "家电清洗", "空调 / 洗衣机 / 油烟机任选一台深度清洗。", 800, 10),
)


def ensure_merchant_tables() -> None:
    """幂等迁移：商家端闭环所需的 5 张表 + 索引 + 1 个补列。

    为什么走这里而不放进 sql/*.sql：
    1. `initialize_schema()` 对每个 sql 文件只做一次 `execute()`（单文件只能写一条语句），
       而这里是 5 张表 + 6 个索引 + 1 个补列，塞进去必然失败；
    2. 它没有 try/except，任何异常都会直接让后端起不来；这里捕获后只记 ERROR，
       商家端接口随后会以明确错误暴露，而不是整个服务不可用；
    3. **纯 INSERT 的种子数据更危险**：`initialize_schema` 每次启动全量执行，
       放 sql/ 里会导致每次重启都重复插 5 家店（详见 ensure_merchant_seed）。

    `audit_reason` 是任务书 5 张表定义之外**唯一新增的一列**：
    管理端审核接口 `PUT /admin/merchant/{id}/audit` 接收 `reason`，
    没有这一列这个参数就无处落地，商家被拒后也看不到原因。
    列可空、只在新表上追加，不影响任何现有结构。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `merchant` (
                           `id`              BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `user_id`         BIGINT NULL COMMENT '关联的登录账号，可为空（平台代录）',
                           `name`            VARCHAR(100) NOT NULL COMMENT '店铺名',
                           `category`        VARCHAR(50) NULL COMMENT '类型：打印/便利店/理发/回收/家政',
                           `contact`         VARCHAR(100) NULL COMMENT '联系方式',
                           `address`         VARCHAR(200) NULL COMMENT '地址',
                           `description`     TEXT NULL COMMENT '简介',
                           `logo_url`        VARCHAR(500) NULL COMMENT 'LOGO 相对路径（读取时签名）',
                           `status`          TINYINT NOT NULL DEFAULT 0 COMMENT '0待审核 1已通过 2已拒绝 3已停业',
                           `commission_rate` DECIMAL(5,2) NOT NULL DEFAULT 5.00 COMMENT '平台佣金比例%',
                           `audit_reason`    VARCHAR(255) NULL COMMENT '审核意见（拒绝原因，展示给商家）',
                           `created_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           `updated_at`      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                           PRIMARY KEY (`id`),
                           KEY `idx_status_created` (`status`, `created_at`),
                           KEY `idx_category` (`category`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商家表'"""
                )
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `merchant_product` (
                           `id`          BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `merchant_id` BIGINT NOT NULL COMMENT '所属商家',
                           `title`       VARCHAR(100) NOT NULL COMMENT '如"打印券10张"',
                           `description` TEXT NULL COMMENT '详细描述',
                           `image_url`   VARCHAR(500) NULL COMMENT '图片相对路径（读取时签名）',
                           `points_cost` INT NOT NULL COMMENT '兑换所需积分',
                           `stock`       INT NOT NULL DEFAULT 0 COMMENT '库存',
                           `sold_count`  INT NOT NULL DEFAULT 0 COMMENT '已兑换数',
                           `status`      TINYINT NOT NULL DEFAULT 1 COMMENT '1上架 0下架',
                           `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           PRIMARY KEY (`id`),
                           KEY `idx_merchant_status` (`merchant_id`, `status`),
                           KEY `idx_status` (`status`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商家商品/服务表'"""
                )
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `redemption_order` (
                           `id`          BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `order_no`    VARCHAR(32) NOT NULL COMMENT '兑换单号（RD+时间戳+随机数）',
                           `user_id`     BIGINT NOT NULL COMMENT '兑换用户',
                           `merchant_id` BIGINT NOT NULL COMMENT '所属商家',
                           `product_id`  BIGINT NOT NULL COMMENT '兑换的商品',
                           `points_cost` INT NOT NULL COMMENT '消耗积分（下单时快照）',
                           `status`      TINYINT NOT NULL DEFAULT 1 COMMENT '1待核销 2已核销 3已过期 4已取消',
                           `code`        VARCHAR(16) NOT NULL COMMENT '核销码（6 位数字）',
                           `redeemed_at` DATETIME NULL COMMENT '核销时间',
                           `expires_at`  DATETIME NOT NULL COMMENT '过期时间',
                           `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           PRIMARY KEY (`id`),
                           KEY `idx_user_created` (`user_id`, `created_at`),
                           KEY `idx_merchant_status` (`merchant_id`, `status`),
                           KEY `idx_product` (`product_id`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='积分兑换订单表'"""
                )
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `merchant_settlement` (
                           `id`                BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `merchant_id`       BIGINT NOT NULL COMMENT '商家',
                           `period`            VARCHAR(20) NULL COMMENT '结算周期 如2026-10',
                           `redemption_count`  INT NOT NULL DEFAULT 0 COMMENT '核销单数',
                           `points_total`      INT NOT NULL DEFAULT 0 COMMENT '积分总额',
                           `commission_amount` DECIMAL(10,2) NOT NULL DEFAULT 0.00 COMMENT '平台佣金（元）',
                           `status`            TINYINT NOT NULL DEFAULT 0 COMMENT '0待结算 1已结算',
                           `settled_at`        DATETIME NULL COMMENT '结算时间',
                           `created_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           PRIMARY KEY (`id`),
                           KEY `idx_merchant_period` (`merchant_id`, `period`),
                           KEY `idx_status` (`status`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商家结算表'"""
                )
                # 看板缓存表：按决策「建表但本期不写不读」，dashboard 直接实时聚合
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `merchant_stats` (
                           `merchant_id`       BIGINT NOT NULL COMMENT '商家ID（主键）',
                           `view_count`        INT NOT NULL DEFAULT 0 COMMENT '访问量',
                           `redemption_count`  INT NOT NULL DEFAULT 0 COMMENT '核销单数',
                           `unique_user_count` INT NOT NULL DEFAULT 0 COMMENT '去重用户数',
                           `updated_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                           PRIMARY KEY (`merchant_id`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商家数据看板缓存表'"""
                )
                # 补列：老库若已手工建过 merchant 表（无 audit_reason），这里自愈
                _ensure_column(cursor, "merchant", "audit_reason",
                               "audit_reason VARCHAR(255) NULL COMMENT '审核意见（拒绝原因，展示给商家）'")
                if _ensure_index(
                    cursor, "merchant", MERCHANT_USER_UNIQUE_INDEX,
                    f"ALTER TABLE `merchant` ADD UNIQUE KEY {MERCHANT_USER_UNIQUE_INDEX} (`user_id`)",
                ):
                    logger.info("merchant 唯一索引 %s 创建完成", MERCHANT_USER_UNIQUE_INDEX)
                if _ensure_index(
                    cursor, "redemption_order", REDEMPTION_ORDER_NO_UNIQUE_INDEX,
                    f"ALTER TABLE `redemption_order` ADD UNIQUE KEY {REDEMPTION_ORDER_NO_UNIQUE_INDEX} (`order_no`)",
                ):
                    logger.info("redemption_order 唯一索引 %s 创建完成", REDEMPTION_ORDER_NO_UNIQUE_INDEX)
                if _ensure_index(
                    cursor, "redemption_order", REDEMPTION_CODE_UNIQUE_INDEX,
                    f"ALTER TABLE `redemption_order` ADD UNIQUE KEY {REDEMPTION_CODE_UNIQUE_INDEX} (`code`)",
                ):
                    logger.info("redemption_order 唯一索引 %s 创建完成", REDEMPTION_CODE_UNIQUE_INDEX)
    except Exception:  # noqa: BLE001 — 迁移失败不应阻断服务启动
        logger.error("商家端表 / 索引初始化失败", exc_info=True)


def ensure_merchant_seed() -> None:
    """幂等写入商家端模拟数据（5 家商家 + 10 个商品）。

    **为什么不能用 sql/seed_merchants.sql 的纯 INSERT**：
    `initialize_schema()` 每次启动都会把 sql/*.sql 全量再执行一遍，
    纯 INSERT 会导致「重启一次、多 5 家店」。`INSERT IGNORE` 也救不了——
    `merchant` 表没有「店名」唯一键，天然不会冲突。

    因此改成「先按店名整体 COUNT，已存在就整批跳过」：
    - 幂等：重复启动不会重复插入；
    - 不覆盖：管理员改过店名 / 佣金 / 状态后，这里绝不回改（整批跳过）；
    - 失败只记 ERROR，不阻断启动。

    商家 `user_id` 一律 NULL：平台代录的演示数据，不绑定任何真实登录账号。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                names = [row[0] for row in _MERCHANT_SEED]
                placeholders = ", ".join(["%s"] * len(names))
                cursor.execute(
                    f"SELECT COUNT(*) AS c FROM merchant WHERE name IN ({placeholders})",
                    names,
                )
                row = cursor.fetchone()
                if row and int(row.get("c") or 0) > 0:
                    return

                commission = f"{float(settings.merchant_commission_rate):.2f}"
                merchant_placeholders = ", ".join(["(%s, %s, %s, %s, %s, 1, %s)"] * len(_MERCHANT_SEED))
                merchant_params: list = []
                for name, category, contact, address, description in _MERCHANT_SEED:
                    merchant_params.extend([name, category, contact, address, description, commission])
                cursor.execute(
                    f"INSERT INTO merchant (name, category, contact, address, description, status, commission_rate) "
                    f"VALUES {merchant_placeholders}",
                    merchant_params,
                )

                # 回查真实自增 ID，建立「店名 → id」映射（不能假设自增从 1 开始）
                cursor.execute(
                    f"SELECT id, name FROM merchant WHERE name IN ({placeholders})", names
                )
                id_by_name = {r["name"]: int(r["id"]) for r in cursor.fetchall()}

                product_rows = []
                product_params: list = []
                for merchant_name, title, description, points_cost, stock in _MERCHANT_PRODUCT_SEED:
                    merchant_id = id_by_name.get(merchant_name)
                    if not merchant_id:
                        continue
                    product_rows.append("(%s, %s, %s, %s, %s, 1)")
                    product_params.extend([merchant_id, title, description, points_cost, stock])
                if product_rows:
                    cursor.execute(
                        f"INSERT INTO merchant_product "
                        f"(merchant_id, title, description, points_cost, stock, status) "
                        f"VALUES {', '.join(product_rows)}",
                        product_params,
                    )
                logger.info(
                    "商家端种子数据写入完成：%s 家商家 / %s 个商品",
                    len(_MERCHANT_SEED), len(product_rows),
                )
    except Exception:  # noqa: BLE001 — 初始化失败不应阻断服务启动
        logger.error("商家端种子数据写入失败", exc_info=True)


# ============================================================
# 平台回收（二期）：用户「交给平台回收」→ 立即得积分 → 平台库存
# → 运营批量卖给回收商 → 毛利统计
# ============================================================
def ensure_recycle_tables() -> None:
    """幂等迁移：平台回收二期所需 2 张新表 + `item` 2 列。

    为什么走这里而不放进 sql/*.sql：
    1. `initialize_schema()` 对每个 sql 文件只做一次 execute（单文件只能写一条语句），
       而这里是 2 张表 + 2 个补列，塞进去必然失败；
    2. 它没有 try/except，任何异常都会直接让后端起不来；这里捕获后只记 ERROR，
       回收接口随后会以明确错误暴露，而不是整个服务不可用。

    `item` 补列走 `_ensure_column`（幂等）：`accept_points` / `recycle_status`
    均为 NOT NULL DEFAULT，存量行自动落默认值（0 = 不参与回收），无需回填。
    `recycle_no` / `sale_no` 的唯一性由建表语句内联 UNIQUE KEY 保证
    （表是新表，不存在「已存在但缺索引」的老环境）。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `platform_recycle` (
                           `id`             BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `recycle_no`     VARCHAR(32) NOT NULL COMMENT '回收单号（PR+时间戳+随机数）',
                           `user_id`        BIGINT NOT NULL COMMENT '提交用户',
                           `item_id`        BIGINT NOT NULL COMMENT '回收的物品',
                           `points_reward`  INT NOT NULL COMMENT '发放的积分',
                           `pickup_method`  TINYINT NOT NULL DEFAULT 1 COMMENT '1送到回收点 2上门取件',
                           `pickup_address` VARCHAR(200) NULL COMMENT '上门取件地址（method=2 必填）',
                           `status`         TINYINT NOT NULL DEFAULT 1 COMMENT '1待取件 2已入库 3已售出 4已取消',
                           `received_at`    DATETIME NULL COMMENT '入库时间',
                           `sold_at`        DATETIME NULL COMMENT '售出时间',
                           `created_at`     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           PRIMARY KEY (`id`),
                           UNIQUE KEY `uk_recycle_no` (`recycle_no`),
                           KEY `idx_user` (`user_id`, `status`),
                           KEY `idx_status` (`status`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台回收单'"""
                )
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `platform_sale` (
                           `id`           BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `sale_no`      VARCHAR(32) NOT NULL COMMENT '销售单号（PS+时间戳+随机数）',
                           `recycler_id`  BIGINT NOT NULL COMMENT '回收商ID（merchant.category=回收）',
                           `total_amount` DECIMAL(10,2) NOT NULL COMMENT '销售金额',
                           `item_count`   INT NOT NULL COMMENT '物品数量',
                           `items_json`   TEXT NOT NULL COMMENT '物品明细JSON（销售时快照）',
                           `status`       TINYINT NOT NULL DEFAULT 1 COMMENT '1已成交',
                           `created_at`   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           PRIMARY KEY (`id`),
                           UNIQUE KEY `uk_sale_no` (`sale_no`),
                           KEY `idx_recycler` (`recycler_id`),
                           KEY `idx_created_at` (`created_at`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台销售单'"""
                )
                _ensure_column(cursor, "item", "accept_points",
                               "accept_points INT NOT NULL DEFAULT 0 COMMENT '平台回收估价，0表示不参与回收'")
                _ensure_column(cursor, "item", "recycle_status",
                               "recycle_status TINYINT NOT NULL DEFAULT 0 COMMENT '0不参与 1待取件 2已入库 3已售出 4已取消'")
    except Exception:  # noqa: BLE001 — 迁移失败不应阻断服务启动
        logger.error("平台回收表 / 列初始化失败", exc_info=True)


def ensure_demand_table() -> None:
    """幂等迁移：个人中心「我的需求」+ 首页「公开需求墙」所需的 swap_demand 表。

    为什么走这里而不放进 sql/*.sql：
    1. `initialize_schema()` 对每个 sql 文件只做一次 execute（单文件只能写一条语句），
       而建表 + 建索引是多条语句，塞进去必然失败；
    2. 它没有 try/except，任何异常都会直接让后端起不来；这里捕获后只记录 ERROR，
       需求相关接口随后会以明确错误暴露，而不是整个服务不可用。

    为什么必须补索引：
    - `idx_user_status (user_id, status)`：支撑「我的需求」按状态筛选 + 按时间倒序分页；
    - `idx_status_created (status, created_at)`：支撑公开需求墙
      （WHERE status=1 ORDER BY created_at DESC LIMIT n）。
    表本身用 CREATE TABLE IF NOT EXISTS（幂等），索引另用 _ensure_index 判断，
    使「表已存在但索引缺失」的环境也能自愈。
    """
    try:
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """CREATE TABLE IF NOT EXISTS `swap_demand` (
                           `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键',
                           `user_id` BIGINT NOT NULL COMMENT '发布人',
                           `title` VARCHAR(100) NOT NULL COMMENT '需求标题',
                           `description` TEXT COMMENT '详细描述',
                           `category` VARCHAR(50) COMMENT '期望类别',
                           `status` TINYINT NOT NULL DEFAULT 1 COMMENT '1进行中 2已完成 3已撤销',
                           `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                           `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                           PRIMARY KEY (`id`),
                           KEY `idx_user_status` (`user_id`, `status`),
                           KEY `idx_status_created` (`status`, `created_at`)
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户物品需求表'"""
                )
                if _ensure_index(
                    cursor, "swap_demand", DEMAND_USER_STATUS_INDEX,
                    f"ALTER TABLE `swap_demand` ADD KEY {DEMAND_USER_STATUS_INDEX} (user_id, status)",
                ):
                    logger.info("swap_demand 索引 %s 创建完成", DEMAND_USER_STATUS_INDEX)
                if _ensure_index(
                    cursor, "swap_demand", DEMAND_STATUS_CREATED_INDEX,
                    f"ALTER TABLE `swap_demand` ADD KEY {DEMAND_STATUS_CREATED_INDEX} (status, created_at)",
                ):
                    logger.info("swap_demand 索引 %s 创建完成", DEMAND_STATUS_CREATED_INDEX)
    except Exception:  # noqa: BLE001 — 迁移失败不应阻断服务启动
        logger.error("swap_demand 表 / 索引初始化失败", exc_info=True)
