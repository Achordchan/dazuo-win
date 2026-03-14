import inspect
import logging
from typing import Optional

from openai import AsyncOpenAI

from ..fanyi import FanYiJieKou

logger = logging.getLogger(__name__)


class OpenAICompatibleAPI(FanYiJieKou):
    LANG_CODES = {
        "简体中文": "zh-CN",
        "繁体中文": "zh-TW",
        "英语": "en",
        "日语": "ja",
        "韩语": "ko",
        "法语": "fr",
        "德语": "de",
        "西班牙语": "es",
        "俄语": "ru",
        "意大利语": "it",
        "葡萄牙语": "pt",
        "越南语": "vi",
        "泰语": "th",
        "阿拉伯语": "ar",
        "自动检测": "auto",
    }

    def __init__(self, base_url: str, model: str, api_key: str):
        base_url = (base_url or "").strip()
        model = (model or "").strip()
        api_key = (api_key or "").strip()

        if not base_url:
            raise ValueError("未设置模型URL")
        if not model:
            raise ValueError("未设置模型名称")
        if not api_key:
            raise ValueError("未设置API密钥")

        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def close(self):
        close_method = getattr(self.client, "close", None)
        if close_method is None:
            return

        result = close_method()
        if inspect.isawaitable(result):
            await result

    async def health_check(self) -> None:
        await self.fanyi("test", "自动检测", "简体中文")

    async def fanyi(self, text: str, source_lang: str, target_lang: str) -> tuple[str, Optional[str]]:
        if not text:
            return "", None

        if source_lang in ("自动检测", "auto", None, ""):
            user_prompt = (
                f"请将下面文本翻译成{target_lang}。只返回翻译结果，不要添加解释。\n\n" + text
            )
        else:
            user_prompt = (
                f"请将下面{source_lang}文本翻译成{target_lang}。只返回翻译结果，不要添加解释。\n\n" + text
            )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是专业翻译。只返回翻译结果，不要添加任何解释或额外内容。注意：输入里可能包含特殊标记 [[DAZUO_NL]]，它代表换行。你必须原样保留该标记（不要翻译、不要删除、不要新增），并保持其相对位置不变。",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
            top_p=0.95,
        )

        result = response.choices[0].message.content.strip()

        detected_lang: Optional[str] = None
        if source_lang in ("自动检测", "auto", None, ""):
            if any("\u4e00" <= char <= "\u9fff" for char in text):
                detected_lang = "zh-CN"
            elif all(ord(char) < 128 for char in text.replace(" ", "")):
                detected_lang = "en"
            elif any("\u3040" <= char <= "\u30ff" for char in text):
                detected_lang = "ja"

        logger.info(f"检测到的语言: {detected_lang}")
        return result, detected_lang
