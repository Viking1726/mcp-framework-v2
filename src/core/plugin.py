"""
插件基类
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import MCPCore

class Plugin(ABC):
    """插件基类"""
    
    def __init__(self, core: 'MCPCore'):
        self.core = core
        self.name = self.__class__.__name__.replace('Plugin', '').lower()
    
    @abstractmethod
    async def initialize(self):
        """初始化插件"""
        pass
    
    async def shutdown(self):
        """关闭插件（可选实现）"""
        pass
