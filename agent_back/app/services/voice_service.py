"""语音服务：语音识别（ASR）与播报文本构造。

- ASR：paraformer 文件转写，需要公网可达的文件 URL（settings.public_base_url），
  未配置时抛出 RuntimeError，由上层降级为文字输入；
- TTS：由前端 Web Speech API 播报，本模块只负责按模式/语言给出播报文本、分句、语速与音色。
"""
import re
from pathlib import Path

from app.core.config import settings
from app.services import llm_client

# 助老模式：语速 ≤0.8、单句 ≤20 字
ELDERLY_RATE = 0.8
ELDERLY_MAX_LEN = 20
NORMAL_RATE = 1.0

# 前端 Web Speech API 的语音语种（按用户语言选择）
VOICE_BY_LANG = {"zh_CN": "zh-CN", "en_US": "en-US"}


def transcribe(audio_path: Path) -> str:
    """语音转文字。audio_path 需位于 uploads/voice 目录下，以便拼接公网 URL。"""
    if not settings.public_base_url:
        raise RuntimeError("语音识别需要配置公网访问地址（PUBLIC_BASE_URL）")
    file_url = f"{settings.public_base_url}{settings.api_prefix}/static/voice/{audio_path.name}"
    return llm_client.transcribe_audio(file_url)


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
