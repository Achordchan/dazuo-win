import asyncio
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from ..gongju.fanyi import sanitize_error_message

# 公共远程服务（无本地引擎）在 HTTP 429 后各自独立冷却。
REMOTE_COOLDOWN_SERVICES = frozenset({"google", "microsoft", "deepl"})


@dataclass(frozen=True)
class TranslationContext:
    api_name: str
    api_generation: int
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
        # Free local engines (DeepLX/Achord) are easy to hammer while typing.
        self._achord_debounce_ms = 900
        # AI-only short cooldown. Never shared with Google/DeepL/Achord.
        self._ai_rate_limit_cooldown_s = 2.0
        self._ai_rate_limit_until = 0.0
        # Public Google/Microsoft/DeepL endpoints also need their own cooldown after 429.
        self._remote_rate_limit_cooldown_s = 60.0
        self._remote_rate_limit_until: dict[str, float] = {}

        self._translation_task: Optional[asyncio.Task] = None
        self._token_counter = 0
        self._active_token = 0

        self._is_translating = False

        self._active_ai_model_name: Optional[str] = None
        self._active_estimated_ai_tokens: Optional[int] = None

        self._last_ai_model_name: Optional[str] = None
        self._last_ai_estimated_tokens: Optional[int] = None
        self._last_translation_duration_ms: Optional[int] = None
        self._newline_token: str = ""

    def get_last_ai_info(self):
        return self._last_ai_model_name, self._last_translation_duration_ms, self._last_ai_estimated_tokens

    def set_input_text(self, text: str, context: TranslationContext) -> None:
        text = text or ""
        self._input_text = text
        self._context = context

        if text.strip() == "":
            self.cancel(clear_output=True)
            return

        self._debounce_timer.start(self._effective_debounce_ms())

    def translate_now(self, text: str, context: TranslationContext) -> None:
        text = text or ""
        self._input_text = text
        self._context = context
        self._debounce_timer.stop()
        # Cooldown is per service. Achord 429 must not block Google/DeepL/AI.
        remaining_ms = int(self._api_rate_limit_remaining_s(context.api_name) * 1000)
        if remaining_ms > 0:
            self._debounce_timer.start(remaining_ms)
            return
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

    async def cancel_and_wait(self, clear_output: bool) -> None:
        self._debounce_timer.stop()

        task = self._translation_task
        if task is not None:
            task.cancel()
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

        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    def _api_rate_limit_remaining_s(self, api_name: Optional[str] = None) -> float:
        """Return remaining cooldown only for the requested service.

        Achord/DeepLX IP bans stay inside AchordBuiltinAPI. They must never be
        folded into a ViewModel-global timer that also blocks Google/DeepL/AI.
        """
        name = api_name
        if name is None and self._context is not None:
            name = self._context.api_name
        name = str(name or "").strip()

        if name == "achord_builtin":
            remaining = 0.0
            try:
                from ..gongju.fanyi_api.achord_builtin import AchordBuiltinAPI

                remaining = float(AchordBuiltinAPI.rate_limit_remaining_s() or 0.0)
            except Exception:
                api = getattr(self._fanyi, "_fanyi_jiekou", None)
                getter = getattr(api, "rate_limit_remaining_s", None)
                if callable(getter):
                    try:
                        remaining = float(getter() or 0.0)
                    except Exception:
                        remaining = 0.0
            return max(0.0, remaining)

        if name == "openai_compat":
            return max(0.0, float(self._ai_rate_limit_until) - time.monotonic())

        if name in REMOTE_COOLDOWN_SERVICES:
            return max(
                0.0,
                float(self._remote_rate_limit_until.get(name, 0.0)) - time.monotonic(),
            )

        return 0.0

    def rate_limit_remaining_s(self, api_name: Optional[str] = None) -> float:
        """Expose the selected service cooldown to other translation surfaces."""
        return self._api_rate_limit_remaining_s(api_name)

    def _effective_debounce_ms(self) -> int:
        delay = int(self._debounce_ms)
        api_name = self._context.api_name if self._context is not None else None
        if api_name == "achord_builtin":
            delay = max(delay, int(self._achord_debounce_ms))
        remaining_ms = int(self._api_rate_limit_remaining_s(api_name) * 1000)
        return max(delay, remaining_ms)

    def _is_rate_limit_error(self, error: Exception) -> bool:
        status_code = getattr(error, "status_code", None) or getattr(error, "status", None)
        if status_code == 429:
            return True
        msg = str(error or "")
        lowered = msg.lower()
        return (
            " 429" in msg
            or "HTTP 429" in msg
            or "http 429" in lowered
            or "too many requests" in lowered
            or "rate limit" in lowered
            or "ratelimit" in lowered
            or "请求过于频繁" in msg
        )

    def _note_ai_rate_limited(self, cooldown_s: Optional[float] = None) -> float:
        wait_s = float(self._ai_rate_limit_cooldown_s if cooldown_s is None else cooldown_s)
        wait_s = max(1.0, wait_s)
        self._ai_rate_limit_until = max(self._ai_rate_limit_until, time.monotonic() + wait_s)
        return wait_s

    def _note_remote_rate_limited(
        self,
        api_name: Optional[str],
        cooldown_s: Optional[float] = None,
    ) -> float:
        name = str(api_name or "").strip()
        wait_s = float(
            self._remote_rate_limit_cooldown_s if cooldown_s is None else cooldown_s
        )
        wait_s = max(1.0, wait_s)
        if name in REMOTE_COOLDOWN_SERVICES:
            self._remote_rate_limit_until[name] = max(
                self._remote_rate_limit_until.get(name, 0.0),
                time.monotonic() + wait_s,
            )
        return wait_s

    def note_service_rate_limit_error(
        self,
        api_name: Optional[str],
        error: Exception,
    ) -> float:
        """Record a 429 for the service used outside the main translation panel."""
        if not self._is_rate_limit_error(error):
            return 0.0

        name = str(api_name or "").strip()
        if name in REMOTE_COOLDOWN_SERVICES:
            self._note_remote_rate_limited(name)
        elif name == "openai_compat":
            self._note_ai_rate_limited()
        return self._api_rate_limit_remaining_s(name)

    def _on_debounce_timeout(self) -> None:
        # Service-scoped cooldown only. Switching engines clears this wait path.
        api_name = self._context.api_name if self._context is not None else None
        remaining_ms = int(self._api_rate_limit_remaining_s(api_name) * 1000)
        if remaining_ms > 0:
            self._debounce_timer.start(remaining_ms)
            return
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

    def _make_newline_token(self) -> str:
        return f"[[DZFYQ_NL_{secrets.token_hex(8)}]]"

    def _replace_newlines(self, text: str) -> str:
        self._newline_token = self._make_newline_token()
        return self._normalize_newlines(text).replace("\n", f" {self._newline_token} ")

    def _restore_newlines(self, text: str) -> str:
        token = self._newline_token or "[[DZFYQ_NL]]"
        return text.replace(f" {token} ", "\n").replace(token, "\n")

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
                api_name=ctx.api_name,
                api_generation=ctx.api_generation,
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
            self.error_message_changed.emit(None)
            self.output_text_changed.emit(translated)
            self.detected_source_language_changed.emit(detected)

        except asyncio.CancelledError:
            return
        except Exception as e:
            if token != self._active_token:
                return

            msg = self._safe_error_message(e)
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
        api_name: Optional[str] = None,
        api_generation: Optional[int] = None,
    ):
        async def once():
            result = await self._fanyi.fanyi(
                text,
                source_lang,
                target_lang,
                expected_api_name=api_name,
                expected_api_generation=api_generation,
            )
            if isinstance(result, tuple):
                return result
            return result, None

        try:
            return await once()
        except Exception as e:
            if not self._is_rate_limit_error(e):
                raise

            base = self._safe_error_message(e)
            self.error_message_changed.emit(base)
            self.toast_message.emit(base, "warning")

            # Achord/DeepLX: ban window lives in AchordBuiltinAPI only.
            if api_name == "achord_builtin":
                raise

            # Google/DeepL use independent cooldowns. Switching service remains immediate.
            if not is_ai:
                self._note_remote_rate_limited(api_name)
                raise

            # AI providers often recover quickly after a brief AI-only pause.
            wait_s = self._note_ai_rate_limited(self._ai_rate_limit_cooldown_s)
            remaining = int(max(1.0, wait_s))
            while remaining > 0:
                self.toast_message.emit(f"请求过于频繁，{remaining} 秒后重试", "info")
                await asyncio.sleep(1)
                remaining -= 1
                if token != self._active_token:
                    raise

            try:
                return await once()
            except Exception as retry_error:
                if self._is_rate_limit_error(retry_error):
                    self._note_ai_rate_limited(self._ai_rate_limit_cooldown_s)
                raise

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

    def _safe_error_message(self, error: Exception) -> str:
        api = getattr(self._fanyi, "_fanyi_jiekou", None)
        secrets = [getattr(api, "api_key", "")]
        return sanitize_error_message(error, secrets)
