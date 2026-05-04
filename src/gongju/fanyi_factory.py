from ..shezhi import Config
from .fanyi import FanYiJieKou
from .fanyi_api import DeepLAPI, GoogleAPI, OpenAICompatibleAPI


def build_translation_api(config: Config) -> FanYiJieKou:
    api_name = config.get("translation.api", "google")
    if api_name == "google":
        return GoogleAPI()
    if api_name == "deepl":
        api_key = config.get("deepl.api_key", "")
        return DeepLAPI(api_key=api_key)
    if api_name == "openai_compat":
        base_url = config.get("openai_compat.base_url")
        model = config.get("openai_compat.model")
        api_key = config.get("openai_compat.api_key")
        return OpenAICompatibleAPI(base_url=base_url, model=model, api_key=api_key)
    raise ValueError("未知服务")
