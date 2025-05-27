"""
微核心配置系统
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class Config:
    """单一配置管理器"""
    
    def __init__(self, config_path: str = "config.json"):
        self.path = Path(config_path)
        self._data = self._load()
        
    def _load(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            if self.path.exists():
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            return {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分割的嵌套键"""
        keys = key.split('.')
        value = self._data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def __getattr__(self, name: str) -> Any:
        """支持属性访问"""
        return self.get(name, {})

# 全局配置实例
config = Config()
