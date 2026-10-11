"""智能体助手：配置 LLM_API_KEY 后走真实大模型，否则降级本地演示。"""
import time
from collections.abc import Iterator

from app.services import dashscope

SYSTEM_PROMPT = (
    "你是「社区旧物互换平台」的智能助手，名字叫小绿。平台功能简介：用户上传闲置物品（提交后进入待审核），"
    "管理员审核通过后展示在首页轮播和物品列表供邻里浏览；支持手机号/邮箱验证码登录；完成交换可获得积分奖励，"
    "积分是「绿色达人」社区榜单的依据；平台鼓励邻里互助、旧物循环利用、减少碳排放。"
    "请用简洁友好的中文回答与平台使用、旧物交换相关的问题，回答控制在 300 字以内；"
    "无关问题礼貌地引导回平台话题。"
)

# 英文模式追加的语言指令（用户要求：目标语言为 English 时全程英文，禁止中文）
EN_LANGUAGE_DIRECTIVE = (
    "\n\n请务必使用 English 回复用户。目标语言是 English，请全程使用英文回答，禁止出现中文。"
)

# 英文演示回复（LLM 不可用时的降级文案）
EN_MOCK_REPLY = (
    "Hi, I'm Xiao Lyu, the assistant of the community swap platform. I can help with: "
    "how to list a pre-loved item, finding items to swap, arranging handover safely, "
    "green points and the leaderboard, and eco tips. "
    "(Demo mode: configure LLM_API_KEY in .env to enable the real LLM.)"
)

CATEGORIES = ["数码电子", "家居家电", "图书文具", "服饰鞋包", "母婴用品", "运动户外", "美妆个护", "其他闲置"]


def mock_reply(question: str) -> str:
    """无 API Key 时的本地演示回复（按关键词给出贴合平台的指导）。"""
    if any(k in question for k in ("发布", "上传", "挂出", "挂上")):
        return (
            "发布闲置很简单：\n"
            "1. 登录后进入「探索物品」页，点击「上传物品」；\n"
            "2. 填写物品名称、描述、分类和联系方式，最好配一张实物图；\n"
            "3. 提交后进入待审核，管理员审核通过就会出现在首页轮播和物品列表中，邻居看到后就能和你发起交换啦。"
        )
    if any(k in question for k in ("匹配", "想要", "换一本", "找个", "寻找", "换点")):
        return (
            "智能匹配建议：\n"
            "1. 在「探索物品」用分类和关键词筛选心仪物品；\n"
            "2. 点开物品详情查看成色、描述和联系方式，联系对方约定交换；\n"
            "3. 也建议把你的闲置先挂上去，写清「期望交换物」，让有需要的邻居主动找你。"
        )
    if any(k in question for k in ("交接", "地点", "时间", "见面", "安全")):
        return (
            "线下交接小贴士：\n"
            "1. 优先约在社区中心广场、物业门口等人多的公共区域；\n"
            "2. 尽量白天见面，交换前当面试用、检查物品；\n"
            "3. 在平台确认交换完成后，双方都能获得积分奖励。"
        )
    if any(k in question for k in ("积分", "榜单", "达人", "等级")):
        return (
            "积分规则：发布物品、完成交换、每日签到都能获得积分；"
            "积分是「绿色达人」社区榜单的重要依据，本月交换次数越多、收到评价越好，越有机会上榜哦。"
        )
    if any(k in question for k in ("环保", "碳", "绿色", "循环")):
        return (
            "每一件闲置的流转都是一次减碳：平台会根据物品类别和重量估算碳减排量。"
            "旧物循环利用既节省资源又温暖邻里——让闲置物品流动起来，正是我们社区的初心。"
        )
    return (
        "你好，我是社区旧物互换助手小绿～可以帮你解答：如何发布闲置、寻找心仪物品、约定交接、"
        "积分与绿色达人榜单、环保减碳小知识等。（当前为演示模式：后端未配置 LLM_API_KEY，"
        "配置后即可接入真实大模型回答任意问题）"
    )


def stream_tokens(question: str, lang: str = "zh") -> Iterator[str]:
    """流式产出回答；LLM 未配置或首包前失败时回退演示回复。lang 支持 'zh'/'en'。"""
    is_en = lang == "en"
    if dashscope.has_key():
        emitted = False
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT + (EN_LANGUAGE_DIRECTIVE if is_en else "")},
                {"role": "user", "content": question},
            ]
            for token in dashscope.chat_stream(messages):
                emitted = True
                yield token
            return
        except Exception:
            if emitted:
                yield "\n\n（回答生成中断，请重试）" if not is_en else "\n\n(Answer interrupted, please retry.)"
                return
    text = EN_MOCK_REPLY if is_en else mock_reply(question)
    for ch in text:
        yield ch
        time.sleep(0.02)


def _valid_recognition(data: dict) -> dict | None:
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    category = str(data.get("category") or "").strip()
    if category not in CATEGORIES:
        category = "其他闲置"
    try:
        condition = int(data.get("condition_level") or 3)
    except (TypeError, ValueError):
        condition = 3
    condition = max(1, min(5, condition))
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    return {
        "name": name[:64],
        "category": category,
        "condition_level": condition,
        "description": str(data.get("description") or "").strip()[:200],
        "tags": [str(t)[:16] for t in tags][:6],
    }


def mock_recognition() -> dict:
    return {
        "name": "演示识别结果",
        "category": "其他闲置",
        "condition_level": 4,
        "description": "当前为演示模式：在 .env 配置 LLM_VL_MODEL 多模态模型后即可真实识别图片中的物品。",
        "tags": ["演示", "旧物", "环保"],
    }
