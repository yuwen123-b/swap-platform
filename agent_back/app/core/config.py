from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "社区旧物互换智能体平台"
    api_prefix: str = "/api/v1"
    debug: bool = True
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "swap"
    db_charset: str = "utf8mb4"
    db_pool_min_cached: int = 1
    db_pool_max_cached: int = 5
    db_pool_max_connections: int = 20
    jwt_secret: str = "change_me_to_a_long_random_string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Allow Vite's localhost, loopback, and common LAN development origins.
    cors_origin_regex: str = r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    # smtp: 真实发送；mock: 仅打印到后端控制台
    email_provider: str = "smtp"
    sms_provider: str = "mock"
    # 阿里云短信（SMS_PROVIDER=aliyun 时必填）
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""
    sms_sign_name: str = ""
    sms_template_code: str = ""
    # 用户上传图片存储目录（相对 agent_back 运行目录）
    upload_dir: str = "uploads"
    # 大模型（阿里云百炼 DashScope OpenAI 兼容接口；DASHSCOPE_API_KEY 为空时降级演示模式）
    dashscope_api_key: str = ""
    llm_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_model: str = "qwen-plus"
    llm_vl_model: str = "qwen-vl-plus"
    # 图像编辑（视角外推）/ 文生图 / 语音识别模型
    llm_image_edit_model: str = "wanx2.1-imageedit"
    llm_image_gen_model: str = "wanx2.1-t2i-turbo"
    # 语音识别主模型：qwen3-asr-flash（多模态接口，base64 直传，**不需要公网 URL**）
    # 注意：paraformer-realtime-v2 是实时流式模型，录音文件转写不接受它；
    # 本账号实测 paraformer-v2 文件转写返回 SERVER_ERROR（模型未开通），故作为兜底。
    llm_asr_model: str = "qwen3-asr-flash"
    # 兜底：paraformer 录音文件转写（异步任务，需公网可达 URL）
    llm_asr_model_para: str = "paraformer-v2"
    # 语音合成（qwen3-tts-flash 同步 HTTP 接口；合成失败或未配置密钥时自动降级为前端 Web Speech API）
    llm_tts_model: str = "qwen3-tts-flash"
    llm_tts_voice: str = "Cherry"
    # 文本向量模型（Chroma 向量库预留）
    llm_embedding_model: str = "text-embedding-v4"
    # DashScope 原生 REST 接口 URL（异步任务类：图像编辑/文生图/语音识别/任务轮询）
    image_edit_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2image/image-synthesis"
    image_gen_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    tts_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    # 语音识别（qwen3-asr-flash 走多模态接口；paraformer 走上面的 asr_api_url 异步任务）
    asr_multimodal_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    asr_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
    task_api_url: str = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    # 后端公网访问地址（图像编辑、语音识别需向 DashScope 提供公网可达的文件 URL，留空则相关能力自动降级）
    public_base_url: str = ""
    # 魔搭社区（ModelScope）免费 API：每日 2000 次免费调用
    modelscope_api_key: str = ""
    modelscope_api_url: str = "https://api-inference.modelscope.cn/v1"
    # 能力供应商切换：modelscope 或 dashscope（默认 dashscope）
    # 实测魔搭推理网关只有文本模型（/v1/models 37 个），**没有任何音频端点**
    # （/v1/audio/transcriptions、/v1/audio/speech 均 404），故语音能力默认走百炼。
    asr_provider: str = "dashscope"
    tts_provider: str = "dashscope"
    image_provider: str = "modelscope"
    # 魔搭模型 ID（组织/模型名 格式）
    asr_model: str = "FunAudioLLM/Fun-ASR-Nano-2512"
    tts_model: str = "iic/CosyVoice2-0.5B"
    image_model: str = "Qwen/Qwen-Image-Edit-2511"
    # 企业微信机器人 Webhook（留空时推送降级为日志打印，不阻断流程）
    wework_webhook_url: str = ""
    # MCP 服务 SSE URL（mcp-server-chart；留空时 Agent 不注册图表工具）
    mcp_chart_sse_url: str = ""
    # 高德地图 MCP（魔搭部署，streamable_http 传输；留空时 Agent 不注册地图工具）
    mcp_amap_url: str = ""
    # 智能体助手对外名称（改名只需改 .env 的 AGENT_NAME，代码无需改动）
    agent_name: str = "邻里通"
    db_connect_timeout: int = 5
    # 管理端配置
    admin_token_expire_minutes: int = 1440
    ai_monitor_enabled: bool = True
    # 受控文件（图片）签名 URL 有效期（秒）；超出后需重新获取资源地址
    file_url_expire_seconds: int = 3600
    # 高德地图 Web 服务 Key（地址 → 坐标 地理编码；留空时该接口返回 501 并提示配置）
    amap_web_key: str = ""
    # ===== 3D 物品模型生成（图生 3D → GLB，多服务商可切换）=====
    # 总开关：默认关闭。开启后每次生成都会花钱，只在演示时打开。
    # 后端硬校验（api/v1/model.py 与 three_d_service 各判一次），前端绕过也拦得住。
    model_3d_enabled: bool = False
    # 服务商分派：hunyuan（腾讯混元 3D 极速版，默认）| tripo（百炼 Tripo，回退分支）
    model_3d_provider: str = "hunyuan"
    # --- 腾讯混元 3D（TokenHub 网关）---
    # 鉴权是「控制台创建的 API Key（sk- 开头）+ Bearer」，**不是** SecretId/SecretKey 的 TC3 签名；
    # 该网关也没有 region 概念，因此不需要任何腾讯云 SDK，requests 直连即可。
    tokenhub_api_key: str = ""
    tokenhub_api_url: str = "https://tokenhub.tencentmaas.com"
    # hy-3d-express：极速版，官方口径 ≤1 分 30 秒出结果，15~25 积分/次（约 1.8~3 元）
    hunyuan_3d_model: str = "hy-3d-express"
    # PBR 材质（metallic/roughness/normal 贴图）：默认关。开启 +10 积分/次。
    hunyuan_3d_pbr: bool = False
    # 轮询总超时（秒）：官方 ≤90s，留 3.3 倍余量
    hunyuan_3d_timeout_seconds: int = 300
    # 轮询间隔（秒）：Express 结果快，5s 兼顾响应速度与请求量
    hunyuan_3d_poll_interval_seconds: float = 5.0
    # 输入图 base64 上限（字节）：官方限制编码前 ≤6MB
    hunyuan_3d_max_image_bytes: int = 6 * 1024 * 1024
    # --- 百炼 Tripo（回退分支：MODEL_3D_PROVIDER=tripo 时生效）---
    # Tripo/Tripo-P1.0（最高 2 万面、文件小、加载快）
    # 备选 Tripo/Tripo-H3.1（最高 150-200 万面、40MB+，更精细但前端加载慢）
    model_3d_model: str = "Tripo/Tripo-P1.0"
    # 提交端点：文档要求华北2（北京）地域 + 该地域 API Key；通用域在本账号实测可用
    model_3d_api_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/3d-generation"
    )
    # 贴图质量：standard（标清）/ detailed（高清）。注意 geometry_quality 仅 H3.1 支持，
    # 对 P1.0 传它会 400，因此代码里不发送该参数。
    model_3d_texture_quality: str = "standard"
    # 提交→SUCCEEDED 的轮询总超时（秒）：与前端「未完成判 failed」的兜底对齐
    model_3d_timeout_seconds: int = 300
    # 轮询间隔（秒）：文档建议 15s；这里 10s 在查询 RPS 20 限制内兼顾响应速度
    model_3d_poll_interval_seconds: float = 10.0
    # GLB 下载超时（秒）：Tripo 链接 2 小时失效，SUCCEEDED 后必须立即下载
    model_3d_download_timeout_seconds: int = 300
    # ===== 商家端闭环（用户赚积分 → 兑换商家服务 → 商家核销 → 平台结算）=====
    # 总开关：关闭时 /api/v1/merchant 下所有用户/商家侧接口一律 403
    merchant_enabled: bool = True
    # 佣金比例默认值（%）。仅在「新建商家」时作为初始值写入 merchant.commission_rate；
    # 之后一律以 merchant 表那一行为准，管理员可对单店单独调整。
    merchant_commission_rate: float = 5.00
    # 积分 → 现金汇率（元/积分）：100 积分 = 1 元。
    # 结算佣金 = points_total × merchant_points_to_yuan × (commission_rate / 100)
    merchant_points_to_yuan: float = 0.01
    # 核销码有效期（天）：兑换成功后经过该天数仍未核销即视为过期并退还积分
    redemption_code_expire_days: int = 30
    # 过期扫描循环间隔（秒）：默认 3600（每小时一次）
    redemption_expire_interval_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
