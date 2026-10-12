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
    # 大模型（阿里云百炼 DashScope OpenAI 兼容接口；LLM_API_KEY 为空时降级演示模式）
    llm_api_key: str = ""
    llm_api_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_model: str = "qwen-plus"
    llm_vl_model: str = "qwen-vl-plus"
    # 图像编辑（视角外推）/ 文生图 / 语音识别模型
    llm_image_edit_model: str = "wanx2.1-imageedit"
    llm_image_gen_model: str = "wanx2.1-t2i-turbo"
    llm_asr_model: str = "paraformer-realtime-v2"
    # 语音合成（qwen3-tts-flash 同步 HTTP 接口；合成失败或未配置密钥时自动降级为前端 Web Speech API）
    llm_tts_model: str = "qwen3-tts-flash"
    llm_tts_voice: str = "Cherry"
    # 文本向量模型（Chroma 向量库预留）
    llm_embedding_model: str = "text-embedding-v4"
    # DashScope 原生 REST 接口 URL（异步任务类：图像编辑/文生图/语音识别/任务轮询）
    image_edit_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2image/image-synthesis"
    image_gen_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
    tts_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    asr_api_url: str = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
    task_api_url: str = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    # 后端公网访问地址（图像编辑、语音识别需向 DashScope 提供公网可达的文件 URL，留空则相关能力自动降级）
    public_base_url: str = ""
    # 企业微信机器人 Webhook（留空时推送降级为日志打印，不阻断流程）
    wework_webhook_url: str = ""
    db_connect_timeout: int = 5
    # 管理端配置
    admin_token_expire_minutes: int = 1440
    ai_monitor_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
