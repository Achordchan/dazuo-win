import copy
import sys


def get_default_hotkey() -> str:
    return "command+c,c" if sys.platform == "darwin" else "ctrl+c,c"


VENDOR_DEFAULTS = {
    "智谱": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "model": "",
    },
    "通义千问(Qwen)": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "",
    },
    "字节豆包": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "",
    },
    "Google Gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "",
    },
    "自定义": {
        "base_url": "",
        "model": "",
    },
}


DEFAULT_CONFIG = {
    "theme": "dark",
    "window": {
        "width": 857,
        "height": 620,
        "x": None,
        "y": None,
    },
    "shortcuts": {
        "copy_translate": get_default_hotkey(),
    },
    "display": {
        "source_font_size": 18,
        "target_font_size": 18,
    },
    "auto_start": False,
    "show_in_dock": True,
    "mac_accessibility_prompted": False,
    "translation": {
        "api": "google",
        "source_lang": "自动检测",
        "target_lang": "简体中文",
        "last_working_configs": {},
    },
    "deepl": {
        "api_key": "",
        "account_type": "",
    },
    "microsoft": {
        "api_key": "",
        "region": "",
    },
    "openai_compat": {
        "vendor": "智谱",
        "base_url": VENDOR_DEFAULTS["智谱"]["base_url"],
        "model": VENDOR_DEFAULTS["智谱"]["model"],
        "api_key": "",
        "profiles": {},
    },
}


def build_default_config():
    return copy.deepcopy(DEFAULT_CONFIG)
