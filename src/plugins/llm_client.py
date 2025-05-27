"""
LLM客户端插件 - 精简版
"""
import asyncio
import aiohttp
import json
import logging
from typing import AsyncIterator, Dict, Any, Optional
from openai import AsyncOpenAI

from ..core.plugin import Plugin
from ..core.config import config
from ..core.models import ChatRequest

logger = logging.getLogger(__name__)

class LLMClientPlugin(Plugin):
    """LLM客户端插件"""
    
    def __init__(self, core):
        super().__init__(core)
        self.client: Optional[AsyncOpenAI] = None
        self.service_type = ""
        
    async def initialize(self):
        """初始化LLM客户端"""
        base_url = config.get('llm.base_url')
        api_key = config.get('llm.api_key', 'dummy-key')
        
        # 简单的服务类型检测
        self.service_type = self._detect_service_type(base_url)
        
        # 创建客户端
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=config.get('llm.timeout', 300)
        )
        
        logger.info(f"LLM客户端初始化完成: {self.service_type}")
    
    def _detect_service_type(self, base_url: str) -> str:
        """检测服务类型"""
        base_url = base_url.lower()
        if "dashscope" in base_url or "qwen" in base_url:
            return "qwen"
        elif "ollama" in base_url:
            return "ollama"
        elif "anthropic" in base_url:
            return "anthropic"
        else:
            return "openai"
    
    async def chat_completion(self, request: ChatRequest) -> AsyncIterator[Dict[str, Any]]:
        """聊天完成"""
        try:
            # 准备请求参数
            kwargs = {
                "model": request.model or config.get('llm.model'),
                "messages": [msg.dict(exclude_none=True) for msg in request.messages],
                "stream": True,
                "temperature": request.temperature,
            }
            
            # 添加可选参数
            if request.max_tokens:
                kwargs["max_tokens"] = request.max_tokens
            if request.tools:
                kwargs["tools"] = request.tools
                kwargs["tool_choice"] = request.tool_choice
            
            # 调用API
            stream = await self.client.chat.completions.create(**kwargs)
            
            async for chunk in stream:
                yield chunk.model_dump()
                
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            # 返回错误响应
            yield {
                "choices": [{
                    "delta": {"content": f"错误: {str(e)}"},
                    "index": 0,
                    "finish_reason": "error"
                }]
            }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            models = await self.client.models.list()
            return len(models.data) > 0
        except:
            return False
