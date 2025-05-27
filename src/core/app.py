"""
微核心应用框架
"""
import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import config
import time

logger = logging.getLogger(__name__)

class MCPCore:
    """微核心框架"""
    
    def __init__(self):
        self.plugins: Dict[str, Any] = {}
        self.app = self._create_app()
        
    def _create_app(self) -> FastAPI:
        """创建FastAPI应用"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # 启动时初始化插件
            await self._startup()
            yield
            # 关闭时清理插件
            await self._shutdown()
            
        app = FastAPI(
            title="MCP Framework v2",
            version="2.0.0",
            lifespan=lifespan
        )
        
        # 添加CORS中间件
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # 允许所有源
            allow_credentials=True,
            allow_methods=["*"],  # 允许所有方法
            allow_headers=["*"],  # 允许所有头
        )
        
        # 基础路由
        @app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "plugins": list(self.plugins.keys())
            }
        
        # 模型列表路由
        @app.get("/v1/models")
        async def list_models():
            llm_client = self.get_plugin('llm_client')
            if llm_client:
                # 返回默认模型列表
                return {
                    "object": "list",
                    "data": [
                        {
                            "id": config.get('llm.model', 'default'),
                            "object": "model",
                            "created": 1677610602,
                            "owned_by": "mcp-framework-v2"
                        }
                    ]
                }
            return {"object": "list", "data": []}
        
        @app.get("/models")
        async def list_models_compat():
            return await list_models()
            
        return app
    
    async def _startup(self):
        """启动插件"""
        logger.info("启动MCP核心框架...")
        
        # 动态加载插件
        await self._load_plugins()
        
        logger.info(f"已加载 {len(self.plugins)} 个插件")
    
    async def _shutdown(self):
        """关闭插件"""
        logger.info("关闭MCP核心框架...")
        
        for name, plugin in self.plugins.items():
            if hasattr(plugin, 'shutdown'):
                try:
                    await plugin.shutdown()
                except Exception as e:
                    logger.error(f"插件 {name} 关闭失败: {e}")
    
    async def _load_plugins(self):
        """加载插件"""
        # 这里先加载核心插件，后续可以动态扫描
        from ..plugins.llm_client import LLMClientPlugin
        from ..plugins.mcp_manager import MCPManagerPlugin
        from ..plugins.chat_handler import ChatHandlerPlugin
        
        # 按依赖顺序加载插件
        plugins = [
            ("llm_client", LLMClientPlugin),
            ("mcp_manager", MCPManagerPlugin), 
            ("chat_handler", ChatHandlerPlugin),
        ]
        
        for name, plugin_class in plugins:
            try:
                plugin = plugin_class(self)
                await plugin.initialize()
                self.plugins[name] = plugin
                logger.info(f"已加载插件: {name}")
            except Exception as e:
                logger.error(f"插件 {name} 加载失败: {e}")
    
    def get_plugin(self, name: str):
        """获取插件"""
        return self.plugins.get(name)

# 全局核心实例
core = MCPCore()
