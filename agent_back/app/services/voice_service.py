"""语音服务：语音识别（ASR）、语音合成（TTS）与播报文本构造。

- ASR：paraformer 文件转写，需要公网可达的文件 URL（settings.public_base_url），
  未配置时抛出 RuntimeError，由上层降级为文字输入；
- TTS：qwen-tts 同步合成（llm_client.synthesize_speech），音频落盘 uploads/tts/
  并按真实容器补正扩展名、返回带 HMAC 签名的静态 URL；未配置密钥或合成失败时
  返回空串，前端降级 Web Speech API；
- 播报文本：按模式/语言给出分句、语速与音色（助老模式语速 0.8、单句 ≤20 字）。
"""
import hashlib
import logging
import re
from pathlib import Path

from app.core.config import settings
from app.core.security import sign_file_path
from app.services import llm_client

log = logging.getLogger(__name__)

# 助老模式：语速 ≤0.8、单句 ≤20 字
ELDERLY_RATE = 0.8
ELDERLY_MAX_LEN = 20
NORMAL_RATE = 1.0

# TTS 音频存储目录（位于 uploads/ 下，经 /api/v1/static 挂载对外）
TTS_DIR_NAME = "tts"

# 静态路由按扩展名给 Content-Type 并强制 nosniff，所以扩展名必须与容器真实一致：
# 否则 iOS Safari 会因为「audio/mpeg 的响应体其实是 RIFF」拒绝解码。
# 白名单与 api/v1/files.py 的 _EXT_CONTENT_TYPES 保持一致。
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".ogg", ".flac")

# 小于该字节数的音频视为坏产物（实测出现过 5 字节的 "audio" 被写进缓存，
# 命中后每次都播不出来，且永远不会被重新合成）
MIN_AUDIO_BYTES = 256


def audio_ext(raw: bytes) -> str:
    """按文件头魔数判断音频容器，返回扩展名；无法识别返回空串。

    供应商口径并不统一：百炼 qwen3-tts-flash 返回 WAV，魔搭 CosyVoice 返回 MP3，
    同一套代码两种容器都可能出现，只能看字节，不能看扩展名或 Content-Type。
    """
    head = raw[:16]
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return ".wav"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return ".m4a"
    if head[:3] == b"ID3":
        return ".mp3"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        # MPEG 音频帧同步字（0xFFEx / 0xFFFx），无 ID3 头的裸 MP3 常见形态
        return ".mp3"
    if head[:4] == b"OggS":
        return ".ogg"
    if head[:4] == b"fLaC":
        return ".flac"
    return ""


def _signed_url(filename: str) -> str:
    """拼出可直连的静态 URL：静态路由要求 HMAC 签名，不签名一律 403。"""
    relative = f"{TTS_DIR_NAME}/{filename}"
    return f"{settings.api_prefix}/static/{relative}?{sign_file_path(relative)}"


def _reuse_cached(tts_dir: Path, base: str) -> str:
    """命中已有缓存则返回 URL；顺带修正历史上「扩展名与内容不符」的坏缓存。

    旧实现固定写 .mp3，但实际字节多为 RIFF/WAV：这类文件既播不出来（MIME 不符），
    又会因为文件名固定而永久命中。这里按内容改名，坏字节（长度/魔数不合法）直接删除。
    """
    for ext in AUDIO_EXTS:
        cached = tts_dir / f"{base}{ext}"
        if not cached.is_file():
            continue
        try:
            raw = cached.read_bytes()
        except OSError:
            continue
        real = audio_ext(raw)
        if len(raw) < MIN_AUDIO_BYTES or not real:
            log.warning("TTS 缓存损坏，已删除：%s（%d 字节）", cached.name, len(raw))
            cached.unlink(missing_ok=True)
            continue
        if real != cached.suffix:
            fixed = tts_dir / f"{base}{real}"
            cached.replace(fixed)  # Path.replace 在 Windows 上同样可覆盖
            log.info("TTS 缓存扩展名补正：%s -> %s", cached.name, fixed.name)
            cached = fixed
        return _signed_url(cached.name)
    return ""


def synthesize(text: str, lang: str = "zh_CN", rate: float = 1.0) -> str:
    """语音合成：生成回复音频文件并返回带签名的静态 URL；任何失败降级为空串。

    - 文件按 (lang, rate, text) 摘要命名，同文本命中缓存不重复合成；
    - rate 仅参与缓存键（qwen-tts 不支持语速参数，慢语速由前端浏览器兜底播报保障）；
    - 扩展名由真实容器决定（.wav/.mp3/...），保证静态路由发出的 Content-Type 正确；
    - 返回相对路径（如 /api/v1/static/tts/xxx.wav?exp=..&sig=..），与图片同一签名规则。
    """
    text = (text or "").strip()
    if not text or not (settings.dashscope_api_key or settings.modelscope_api_key):
        return ""
    base = hashlib.md5(f"{lang}|{rate}|{text}".encode("utf-8")).hexdigest()
    tts_dir = Path(settings.upload_dir) / TTS_DIR_NAME

    cached_url = _reuse_cached(tts_dir, base)
    if cached_url:
        return cached_url

    try:
        audio = llm_client.synthesize_speech(text)
    except Exception:  # TTS 属增强能力：未开通/网络失败等一律静默降级
        return ""
    ext = audio_ext(audio or b"")
    if not ext or len(audio) < MIN_AUDIO_BYTES:
        # 不能把无法识别的字节落盘：一旦缓存，这段文本将永远播不出来
        log.warning("TTS 返回非音频内容（%d 字节），已放弃缓存", len(audio or b""))
        return ""
    audio_path = tts_dir / f"{base}{ext}"
    try:
        tts_dir.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(audio)
    except OSError:
        return ""
    return _signed_url(audio_path.name)


# 前端 Web Speech API 的语音语种（按用户语言选择）
VOICE_BY_LANG = {"zh_CN": "zh-CN", "en_US": "en-US"}


def transcribe(audio_path: Path) -> str:
    """语音转文字。audio_path 需位于 uploads/voice 目录下，以便拼接公网 URL。"""
    file_url = ""
    if settings.public_base_url:
        file_url = f"{settings.public_base_url}{settings.api_prefix}/static/voice/{audio_path.name}"
    return llm_client.transcribe_audio(audio_path, file_url)


def _split_sentences(text: str, max_len: int) -> list[str]:
    """按标点分句，再按长度硬切，保证每句不超过 max_len。"""
    parts = re.split(r"(?<=[。！？!?；;，,.])\s*", text)
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        while len(part) > max_len:
            sentences.append(part[:max_len])
            part = part[max_len:]
        sentences.append(part)
    return sentences


def build_speech_text(text: str, mode: str = "normal", language: str = "zh_CN") -> dict:
    """构造前端播报参数：分句文本、语速、音色。

    elderly 模式：语速 0.8、单句不超过 20 字；normal 模式整句播报。
    """
    text = (text or "").strip()
    if mode == "elderly":
        sentences = _split_sentences(text, ELDERLY_MAX_LEN)
        rate = ELDERLY_RATE
    else:
        sentences = [text] if text else []
        rate = NORMAL_RATE
    return {
        "text": text,
        "sentences": sentences,
        "rate": rate,
        "voice": VOICE_BY_LANG.get(language, VOICE_BY_LANG["zh_CN"]),
    }
