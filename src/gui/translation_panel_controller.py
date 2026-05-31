import logging

from ..viewmodels.translator_viewmodel import TranslationContext

logger = logging.getLogger(__name__)


class TranslationPanelController:
    def __init__(self, main_window):
        self.main_window = main_window
        self._active_error_message = None

    def bind_view_model(self) -> None:
        vm = self.main_window.translator_vm
        vm.output_text_changed.connect(self.on_output_text_changed)
        vm.is_translating_changed.connect(self.on_is_translating_changed)
        vm.error_message_changed.connect(self.on_error_message_changed)
        vm.detected_source_language_changed.connect(self.on_detected_source_language_changed)
        vm.ai_phase_changed.connect(self.on_ai_phase_changed)
        vm.estimated_ai_tokens_changed.connect(self.on_estimated_ai_tokens_changed)
        vm.toast_message.connect(self.on_toast_message)

    def build_context(self) -> TranslationContext:
        api_name = self.main_window.config.get("translation.api", "google")
        source_lang = self.main_window.source_lang_combo.currentText().split(" (")[0]
        target_lang = self.main_window.target_lang_combo.currentText()
        ai_model_name = None
        if api_name == "openai_compat":
            ai_model_name = self.main_window.config.get("openai_compat.model")
        return TranslationContext(
            api_name=api_name,
            api_generation=getattr(self.main_window.fanyi, "current_api_generation", 0),
            source_lang=source_lang,
            target_lang=target_lang,
            ai_model_name=ai_model_name,
        )

    def on_input_text_changed(self) -> None:
        text = self.main_window.input_text.toPlainText()
        self.main_window.translator_vm.set_input_text(text, self.build_context())

    def start_translation(self) -> None:
        self.main_window.translator_vm.translate_now(
            self.main_window.input_text.toPlainText(),
            self.build_context(),
        )

    def on_output_text_changed(self, text: str) -> None:
        output = self.main_window.output_text
        output.stop_loading()
        output.setPlainText(text or "")
        self.main_window.switch_button.setEnabled(bool((text or "").strip()))

        if not (text or "").strip():
            output.clear_ai_info()
            return

        if self.main_window.config.get("translation.api", "google") != "openai_compat":
            output.clear_ai_info()
            return

        model, duration_ms, estimated_tokens = self.main_window.translator_vm.get_last_ai_info()
        if model and duration_ms is not None:
            output.set_ai_info(model=model, duration_ms=duration_ms, estimated_tokens=estimated_tokens)
        else:
            output.clear_ai_info()

    def on_is_translating_changed(self, translating: bool) -> None:
        if translating:
            self.main_window.output_text.start_loading()
            self.main_window.output_text.clear_ai_info()
            self.main_window.status_indicator.set_status("normal", "正在翻译...")

            if self.main_window.config.get("translation.api", "google") == "openai_compat":
                model = self.main_window.config.get("openai_compat.model")
                self.main_window.ai_status_bar.set_context(
                    model=model,
                    phase=self.main_window._latest_ai_phase_text,
                    estimated_tokens=self.main_window._latest_ai_estimated_tokens,
                )
                self.main_window.ai_status_bar.start()
            else:
                self.main_window.ai_status_bar.stop()
            return

        self.main_window.output_text.stop_loading()
        if self._active_error_message:
            self.main_window.status_indicator.set_status("error", self._active_error_message)
        else:
            self.main_window.status_indicator.set_status("normal")
        self.main_window.ai_status_bar.stop()

    def on_error_message_changed(self, message) -> None:
        if message:
            self._active_error_message = str(message)
            self.main_window.output_text.stop_loading()
            self.main_window.switch_button.setEnabled(False)
            self.main_window.status_indicator.set_status("error", self._active_error_message)
            return

        self._active_error_message = None
        if not getattr(self.main_window.translator_vm, "_is_translating", False):
            self.main_window.status_indicator.set_status("normal")

    def on_detected_source_language_changed(self, detected_lang) -> None:
        if not detected_lang:
            self.main_window._reset_source_lang_text()
            return

        try:
            api = self.main_window.fanyi._fanyi_jiekou
            detected_map = getattr(api, "DETECTED_LANG_CODES", None)
            if isinstance(detected_map, dict):
                detected_name = detected_map.get(detected_lang, detected_lang)
            else:
                lang_map = {v: k for k, v in getattr(api, "LANG_CODES", {}).items()}
                detected_name = lang_map.get(detected_lang, detected_lang)
            self.main_window._detected_lang = detected_lang
            self.main_window._detected_lang_text = f"自动检测 ({detected_name})"
            self.main_window.source_lang_combo.setItemText(0, self.main_window._detected_lang_text)
        except Exception as error:
            logger.error(f"更新语言检测显示失败: {error}")

    def on_ai_phase_changed(self, phase) -> None:
        self.main_window._latest_ai_phase_text = str(phase) if phase else None
        if phase:
            self.main_window.status_indicator.set_status("normal", str(phase))

        if self.main_window.config.get("translation.api", "google") == "openai_compat" and getattr(self.main_window, "ai_status_bar", None):
            model = self.main_window.config.get("openai_compat.model")
            self.main_window.ai_status_bar.set_context(
                model=model,
                phase=self.main_window._latest_ai_phase_text,
                estimated_tokens=self.main_window._latest_ai_estimated_tokens,
            )

    def on_estimated_ai_tokens_changed(self, estimated) -> None:
        self.main_window._latest_ai_estimated_tokens = estimated
        if self.main_window.config.get("translation.api", "google") == "openai_compat" and getattr(self.main_window, "ai_status_bar", None):
            model = self.main_window.config.get("openai_compat.model")
            self.main_window.ai_status_bar.set_context(
                model=model,
                phase=self.main_window._latest_ai_phase_text,
                estimated_tokens=self.main_window._latest_ai_estimated_tokens,
            )

    def on_toast_message(self, message: str, toast_type: str) -> None:
        if hasattr(self.main_window, "tishi"):
            self.main_window.tishi.showMessage(message, type=toast_type)
