from ..shezhi import Config
from .fanyi import FanYiJieKou, TranslationServiceError
from .fanyi_api import AchordBuiltinAPI, DeepLAPI, GoogleAPI, MicrosoftAPI, OpenAICompatibleAPI


SERVICE_DISPLAY_NAMES = {
    "google": "Google",
    "microsoft": "微软翻译",
    "deepl": "DeepL",
    "achord_builtin": "Achord 内置引擎",
    "openai_compat": "AI（通用接口）",
}


def build_translation_api(config: Config) -> FanYiJieKou:
    api_name = config.get("translation.api", "google")
    if api_name == "google":
        return GoogleAPI()
    if api_name == "microsoft":
        return MicrosoftAPI(
            api_key=config.get("microsoft.api_key", ""),
            region=config.get("microsoft.region", ""),
        )
    if api_name == "deepl":
        api_key = config.get("deepl.api_key", "")
        return DeepLAPI(api_key=api_key)
    if api_name == "achord_builtin":
        return AchordBuiltinAPI()
    if api_name == "openai_compat":
        base_url = config.get("openai_compat.base_url")
        model = config.get("openai_compat.model")
        api_key = config.get("openai_compat.api_key")
        return OpenAICompatibleAPI(base_url=base_url, model=model, api_key=api_key)
    raise TranslationServiceError(f"未知的翻译服务：{api_name}", kind="config")
