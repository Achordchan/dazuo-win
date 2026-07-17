import inspect
import logging
from typing import Optional

from openai import AsyncOpenAI

from ..fanyi import FanYiJieKou, sanitize_error_message

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

    def _status_code(self, error: Exception):
        return getattr(error, "status_code", None) or getattr(error, "status", None)

    def _is_missing_models_endpoint(self, error: Exception) -> bool:
        status = self._status_code(error)
        # When the provider returns an explicit status, only missing-route
        # responses may fall back to a chat probe.
        if status is not None:
            return status in (404, 405)

        message = str(error or "").lower()
        # No status code: require a missing-route signal, not auth/server noise.
        route_markers = (
            "not found",
            "method not allowed",
            "/models",
            "no route",
            "unknown url",
            "404",
            "405",
        )
        auth_or_server_markers = (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "invalid api key",
            "authentication",
            "permission",
            "500",
            "502",
            "503",
            "504",
            "bad gateway",
            "service unavailable",
        )
        if any(marker in message for marker in auth_or_server_markers):
            return False
        return any(marker in message for marker in route_markers)

    def _extract_model_ids(self, response) -> list[str]:
        """Collect model ids from an OpenAI-compatible models.list response."""
        ids: list[str] = []
        if response is None:
            return ids

        data = getattr(response, "data", None)
        if data is None and isinstance(response, dict):
            data = response.get("data")
        if data is None:
            # Some SDKs make the response itself iterable.
            try:
                data = list(response)
            except TypeError:
                data = []

        for item in data or []:
            model_id = getattr(item, "id", None)
            if model_id is None and isinstance(item, dict):
                model_id = item.get("id") or item.get("model")
            if model_id is None and isinstance(item, str):
                model_id = item
            text = str(model_id or "").strip()
            if text:
                ids.append(text)
        return ids

    def _model_listed(self, model_ids: list[str], model: str) -> bool:
        """Only accept the exact configured model id.

        Suffix matching is unsafe: a catalog entry like openai/gpt-4o must not
        make a misconfigured gpt-4o look healthy, because chat may still reject it.
        """
        wanted = (model or "").strip()
        if not wanted:
            return False
        return wanted in model_ids

    async def _probe_chat_model(self) -> None:
        await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )

    async def health_check(self) -> None:
        if not self.base_url or not self.model or not str(self.api_key or "").strip():
            raise ValueError("AI 翻译配置不完整")

        models = getattr(self.client, "models", None)
        if models is not None and hasattr(models, "list"):
            try:
                response = await models.list()
            except Exception as error:
                # Some OpenAI-compatible providers only expose chat completions.
                if not self._is_missing_models_endpoint(error):
                    message = sanitize_error_message(error, [self.api_key])
                    raise ValueError(f"AI 服务健康检查失败: {message}") from error
                logger.info("models.list unsupported for %s; falling back to chat probe", self.base_url)
            else:
                model_ids = self._extract_model_ids(response)
                if model_ids:
                    if self._model_listed(model_ids, self.model):
                        return
                    # Model catalog is available but does not include the configured model.
                    raise ValueError(
                        f"AI 服务已连接，但模型不可用: {self.model}"
                    )
                # Empty/unparseable catalog: still prove the configured model is callable.
                logger.info(
                    "models.list returned no usable ids for %s; probing chat with model %s",
                    self.base_url,
                    self.model,
                )
                try:
                    await self._probe_chat_model()
                    return
                except Exception as error:
                    message = sanitize_error_message(error, [self.api_key])
                    raise ValueError(f"AI 服务健康检查失败: {message}") from error

        # Fallback probe for endpoints without /models.
        try:
            await self._probe_chat_model()
        except Exception as error:
            message = sanitize_error_message(error, [self.api_key])
            raise ValueError(f"AI 服务健康检查失败: {message}") from error

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

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业翻译。只返回翻译结果，不要添加任何解释或额外内容。注意：输入里可能包含特殊标记 [[DZFYQ_NL_*]]，它代表换行。你必须原样保留该标记（不要翻译、不要删除、不要新增），并保持其相对位置不变。",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=2000,
                top_p=0.95,
            )
        except Exception as error:
            message = sanitize_error_message(error, [self.api_key])
            status_code = getattr(error, "status_code", None) or getattr(error, "status", None)
            if status_code:
                raise ValueError(f"AI翻译失败: HTTP {status_code} {message}".strip()) from error

            error_type = type(error).__name__.lower()
            if "timeout" in error_type:
                raise ValueError("AI翻译请求超时，请检查网络连接、代理或服务商状态") from error
            if "connection" in error_type or "connect" in error_type:
                raise ValueError("无法连接到 AI 翻译服务，请检查网络连接、代理或模型 URL") from error
            raise ValueError(f"AI翻译失败: {message}") from error

        try:
            result = (response.choices[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError) as error:
            raise ValueError("AI未返回翻译结果") from error
        if not result:
            raise ValueError("AI未返回翻译结果")

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
