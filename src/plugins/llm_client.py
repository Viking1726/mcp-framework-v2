"""
LLM客户端插件 - 精简版
"""
import logging
from datetime import time
from typing import AsyncIterator, Dict, Any, Optional

from openai import AsyncOpenAI
from ..core.config import config
from ..core.models import ChatRequest, ModelListResponse, ModelObject
from ..core.plugin import Plugin

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
        # self.service_type = self._detect_service_type(base_url)

        # 创建客户端
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=config.get('llm.timeout', 300)
        )

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

    async def get_models(self) -> Optional[ModelListResponse]:
        """获取可用模型列表"""

        # 使用OpenAI SDK获取模型列表
        try:
            models_response = await self.client.models.list()
            model_objects = []
            for model in models_response.data:
                model_objects.append(
                    ModelObject(
                        id=model.id,
                        object="model",
                        created=int(model.created or time.time()),
                        owned_by=model.owned_by or "unknown"
                    )
                )

            if model_objects:
                return ModelListResponse(
                    object="list",
                    data=model_objects
                )
        except Exception as e:
            logger.error(f"SDK获取模型列表失败: {e}")


    async def health_check(self) -> bool:
        """健康检查"""
        try:
            models = await self.client.models.list()
            return len(models.data) > 0
        except:
            return False
