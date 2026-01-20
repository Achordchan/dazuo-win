"""
主题管理模块
"""

from .dark import STYLE as DARK_STYLE
from .light import STYLE as LIGHT_STYLE
from .pink import STYLE as PINK_STYLE

class ThemeManager:
    """主题管理器"""
    
    THEMES = {
        "深色主题": DARK_STYLE,
        "浅色主题": LIGHT_STYLE,
        "粉色主题": PINK_STYLE
    }
    
    @classmethod
    def get_theme_names(cls):
        """获取所有主题名称"""
        return list(cls.THEMES.keys())
    
    @classmethod
    def get_theme_style(cls, theme_name):
        """获取指定主题的样式表
        
        Args:
            theme_name: 主题名称
            
        Returns:
            str: 主题样式表
        """
        return cls.THEMES.get(theme_name, DARK_STYLE)  # 默认返回深色主题 