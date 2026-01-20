import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


@dataclass(frozen=True)
class TranslationContext:
    api_name: str
    source_lang: str
    target_lang: str
    ai_model_name: Optional[str]


class TranslatorViewModel(QObject):
    output_text_changed = pyqtSignal(str)
    is_translating_changed = pyqtSignal(bool)
    error_message_changed = pyqtSignal(object)
    detected_source_language_changed = pyqtSignal(object)
    ai_phase_changed = pyqtSignal(object)
    estimated_ai_tokens_changed = pyqtSignal(object)
    last_translation_duration_ms_changed = pyqtSignal(object)
    toast_message = pyqtSignal(str, str)

    def __init__(self, fanyi, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._fanyi = fanyi
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)

        self._input_text: str = ""
        self._context: Optional[TranslationContext] = None

        self._debounce_ms = 380

        self._translation_task: Optional[asyncio.Task] = None
        self._token_counter = 0
        self._active_token = 0

        self._is_translating = False

        self._active_ai_model_name: Optional[str] = None
        self._active_estimated_ai_tokens: Optional[int] = None

        self._last_ai_model_name: Optional[str] = None
        self._last_ai_estimated_tokens: Optional[int] = None
        self._last_translation_duration_ms: Optional[int] = None

    def get_last_ai_info(self):
        return self._last_ai_model_name, self._last_translation_duration_ms, self._last_ai_estimated_tokens

    def set_input_text(self, text: str, context: TranslationContext) -> None:
        text = text or ""
        self._input_text = text
        self._context = context

        if text.strip() == "":
            self.cancel(clear_output=True)
            return

        self._debounce_timer.start(self._debounce_ms)

    def translate_now(self, text: str, context: TranslationContext) -> None:
        text = text or ""
        self._input_text = text
        self._context = context
        self._debounce_timer.stop()
        self._start_translate_task()

    def cancel(self, clear_output: bool) -> None:
        self._debounce_timer.stop()
        if self._translation_task is not None:
            self._translation_task.cancel()
            self._translation_task = None

        self._token_counter += 1
        self._active_token = self._token_counter

        self._set_is_translating(False)
        self.ai_phase_changed.emit(None)
        self.estimated_ai_tokens_changed.emit(None)
        self.last_translation_duration_ms_changed.emit(None)
        self.detected_source_language_changed.emit(None)
        self.error_message_changed.emit(None)

        self._active_ai_model_name = None
        self._active_estimated_ai_tokens = None

        if clear_output:
            self.output_text_changed.emit("")

    def _on_debounce_timeout(self) -> None:
        self._start_translate_task()

    def _start_translate_task(self) -> None:
        if self._context is None:
            return

        if self._translation_task is not None:
            self._translation_task.cancel()

        self._token_counter += 1
        token = self._token_counter
        self._active_token = token

        self.output_text_changed.emit("")
        self.error_message_changed.emit(None)
        self.detected_source_language_changed.emit(None)
        self.last_translation_duration_ms_changed.emit(None)

        self._last_translation_duration_ms = None

        is_ai = self._context.api_name == "openai_compat"
        if is_ai:
            self._active_ai_model_name = self._context.ai_model_name
            estimated = self._estimate_total_tokens_for_ai(self._input_text, self._context.target_lang)
            self._active_estimated_ai_tokens = estimated
            self.estimated_ai_tokens_changed.emit(estimated)
            self.ai_phase_changed.emit("正在准备请求")
        else:
            self.estimated_ai_tokens_changed.emit(None)
            self.ai_phase_changed.emit(None)

            self._active_ai_model_name = None
            self._active_estimated_ai_tokens = None

        self._set_is_translating(True)

        loop = asyncio.get_event_loop()
        self._translation_task = loop.create_task(self._translate_task(token))

    def _set_is_translating(self, value: bool) -> None:
        if self._is_translating == value:
            return
        self._is_translating = value
        self.is_translating_changed.emit(value)

    def _normalize_newlines(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _replace_newlines(self, text: str) -> str:
        return self._normalize_newlines(text).replace("\n", " [[DAZUO_NL]] ")

    def _restore_newlines(self, text: str) -> str:
        return text.replace(" [[DAZUO_NL]] ", "\n").replace("[[DAZUO_NL]]", "\n")

    async def _translate_task(self, token: int) -> None:
        ctx = self._context
        if ctx is None:
            self._set_is_translating(False)
            return

        raw = self._input_text
        normalized = self._normalize_newlines(raw)
        if normalized.strip() == "":
            if token == self._active_token:
                self.output_text_changed.emit("")
                self._set_is_translating(False)
            return

        text_to_send = self._replace_newlines(normalized)
        is_ai = ctx.api_name == "openai_compat"
        if is_ai:
            self.ai_phase_changed.emit("正在等待服务端响应")

        start = time.monotonic()

        try:
            translated, detected = await self._translate_with_rate_limit_retry(
                text=text_to_send,
                source_lang=ctx.source_lang,
                target_lang=ctx.target_lang,
                token=token,
                is_ai=is_ai,
            )

            if token != self._active_token:
                return

            translated = self._restore_newlines(translated)

            duration_ms = int((time.monotonic() - start) * 1000)

            self._last_translation_duration_ms = duration_ms
            if is_ai:
                self._last_ai_model_name = ctx.ai_model_name
                self._last_ai_estimated_tokens = self._active_estimated_ai_tokens
            else:
                self._last_ai_model_name = None
                self._last_ai_estimated_tokens = None

            self.last_translation_duration_ms_changed.emit(duration_ms)
            self.output_text_changed.emit(translated)
            self.detected_source_language_changed.emit(detected)

        except asyncio.CancelledError:
            return
        except Exception as e:
            if token != self._active_token:
                return

            msg = str(e)
            self.error_message_changed.emit(msg)
            self.toast_message.emit(msg, "error")
        finally:
            if token == self._active_token:
                self._set_is_translating(False)
                self.ai_phase_changed.emit(None)
                self.estimated_ai_tokens_changed.emit(None)

                self._active_ai_model_name = None
                self._active_estimated_ai_tokens = None

    async def _translate_with_rate_limit_retry(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        token: int,
        is_ai: bool,
    ):
        async def once():
            result = await self._fanyi.fanyi(text, source_lang, target_lang)
            if isinstance(result, tuple):
                return result
            return result, None

        try:
            return await once()
        except Exception as e:
            if not is_ai:
                raise

            status_code = getattr(e, "status_code", None) or getattr(e, "status", None)
            msg = str(e)
            is_429 = status_code == 429 or " 429" in msg or "HTTP 429" in msg
            if not is_429:
                raise

            base = msg
            self.error_message_changed.emit(base)
            self.toast_message.emit(base, "warning")

            self.toast_message.emit("准备重试中（2秒）", "info")
            await asyncio.sleep(1)
            if token != self._active_token:
                raise

            self.toast_message.emit("准备重试中（1秒）", "info")
            await asyncio.sleep(1)
            if token != self._active_token:
                raise

            return await once()

    def _estimate_total_tokens_for_ai(self, text: str, target_language: str) -> int:
        system_prompt = "你是一个专业翻译引擎。只输出翻译后的文本，不要解释，不要加前后缀。"
        user_prompt = f"把下面的内容翻译成目标语言（目标语言：{target_language}）。\n\n{text}"
        prompt_tokens = self._estimate_tokens(system_prompt) + self._estimate_tokens(user_prompt)
        completion_tokens = max(64, int(prompt_tokens * 0.55))
        return prompt_tokens + completion_tokens

    def _estimate_tokens(self, text: str) -> int:
        cjk = 0
        for ch in text:
            o = ord(ch)
            if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF:
                cjk += 1
        other = max(0, len(text) - cjk)
        return cjk + int((other + 3) / 4)
