"""
聊天处理插件 - 精简版
"""
import json
import logging
import uuid
from typing import AsyncIterator, Dict, Any, List
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..core.plugin import Plugin
from ..core.models import ChatRequest, ChatMessage

logger = logging.getLogger(__name__)

class ChatHandlerPlugin(Plugin):
    """聊天处理插件"""
    
    def __init__(self, core):
        super().__init__(core)
        self.router = APIRouter()
        
    async def initialize(self):
        """初始化聊天处理器"""
        # 注册路由
        self.router.post("/v1/chat/completions")(self.chat_completions)
        self.router.post("/chat/completions")(self.chat_completions)
        
        # 添加OPTIONS支持（用于CORS预检）
        self.router.options("/v1/chat/completions")(self.handle_options)
        self.router.options("/chat/completions")(self.handle_options)
        
        # 将路由添加到主应用
        self.core.app.include_router(self.router)
        
        logger.info("聊天处理器初始化完成")
    
    async def handle_options(self):
        """处理OPTIONS预检请求"""
        from fastapi import Response
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            }
        )
    
    async def chat_completions(self, request: ChatRequest):
        """聊天完成接口"""
        try:
            # 获取插件
            llm_client = self.core.get_plugin('llm_client')
            mcp_manager = self.core.get_plugin('mcp_manager')
            
            # 增强请求（添加工具）
            if mcp_manager:
                tools = mcp_manager.get_all_tools()
                if tools:
                    request.tools = tools
                    # 添加系统提示
                    system_prompt = self._build_system_prompt(tools)
                    request.messages.insert(0, ChatMessage(
                        role="system", 
                        content=system_prompt
                    ))
            
            # 处理交互式对话
            async def generate():
                async for chunk in self._handle_interactive_chat(request, llm_client, mcp_manager):
                    yield f"data: {json.dumps(chunk)}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
            
        except Exception as e:
            logger.error(f"聊天处理失败: {e}")
            # 返回错误响应
            async def error_response():
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"
            
            return StreamingResponse(error_response(), media_type="text/event-stream")
    
    async def _handle_interactive_chat(self, request: ChatRequest, llm_client, mcp_manager) -> AsyncIterator[Dict[str, Any]]:
        """处理交互式聊天"""
        max_rounds = 5  # 最大交互轮次
        current_request = request
        
        for round_num in range(max_rounds):
            logger.info(f"交互轮次: {round_num + 1}")
            
            # 收集响应状态
            state = {
                "content": "",
                "tool_calls": [],
                "finish_reason": None
            }
            
            # 调用LLM
            async for chunk in llm_client.chat_completion(current_request):
                # 处理响应块
                self._process_chunk(chunk, state)
                
                # 传递给客户端
                yield chunk
                
                # 检查是否需要工具调用
                if state["finish_reason"] == "tool_calls":
                    break
            
            # 如果没有工具调用，结束对话
            if state["finish_reason"] != "tool_calls" or not state["tool_calls"]:
                break
            
            # 执行工具调用
            assistant_msg = ChatMessage(
                role="assistant",
                content=state["content"],
                tool_calls=state["tool_calls"]
            )
            current_request.messages.append(assistant_msg)
            
            # 执行所有工具调用
            for tool_call in state["tool_calls"]:
                await self._execute_tool_call(tool_call, current_request, mcp_manager)
            
            # 添加继续提示
            current_request.messages.append(ChatMessage(
                role="user",
                content="请根据工具执行结果继续回答。"
            ))
    
    def _process_chunk(self, chunk: Dict[str, Any], state: Dict[str, Any]):
        """处理响应块"""
        if not isinstance(chunk, dict) or "choices" not in chunk:
            return
            
        choices = chunk.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            return
            
        choice = choices[0]
        if not isinstance(choice, dict):
            return
        
        # 更新完成原因
        if choice.get("finish_reason"):
            state["finish_reason"] = choice["finish_reason"]
        
        # 处理delta部分
        delta = choice.get("delta", {})
        if not isinstance(delta, dict):
            return
        
        # 收集内容
        if "content" in delta and delta["content"] is not None:
            state["content"] += str(delta["content"])
        
        # 收集工具调用
        if "tool_calls" in delta and delta["tool_calls"] is not None:
            tool_calls = delta["tool_calls"]
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if isinstance(tool_call, dict):
                        self._collect_tool_call(state["tool_calls"], tool_call)
    
    def _collect_tool_call(self, tool_calls: List[Dict], tool_call: Dict):
        """收集工具调用数据"""
        index = tool_call.get("index", 0)
        
        # 确保索引位置存在
        while len(tool_calls) <= index:
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {"name": "", "arguments": ""}
            })
        
        # 更新数据
        if "id" in tool_call:
            tool_calls[index]["id"] = tool_call["id"]
        
        if "function" in tool_call:
            func = tool_call["function"]
            if "name" in func and func["name"] is not None:
                tool_calls[index]["function"]["name"] = func["name"]
            if "arguments" in func and func["arguments"] is not None:
                # 确保参数是字符串类型
                args = func["arguments"]
                if isinstance(args, str):
                    tool_calls[index]["function"]["arguments"] += args
                else:
                    # 如果不是字符串，转换为字符串
                    tool_calls[index]["function"]["arguments"] += str(args)
    
    async def _execute_tool_call(self, tool_call: Dict, request: ChatRequest, mcp_manager):
        """执行工具调用"""
        if not isinstance(tool_call, dict):
            logger.error(f"无效的工具调用数据: {tool_call}")
            return
            
        tool_id = tool_call.get("id", f"call_{uuid.uuid4().hex[:8]}")
        function = tool_call.get("function", {})
        
        if not isinstance(function, dict):
            logger.error(f"无效的函数数据: {function}")
            return
            
        function_name = function.get("name", "")
        arguments = function.get("arguments", "{}")
        
        if not function_name:
            logger.error("工具调用缺少函数名称")
            request.messages.append(ChatMessage(
                role="tool",
                content=json.dumps({"error": "工具调用缺少函数名称"})
            ))
            return
        
        try:
            # 解析参数
            if isinstance(arguments, str):
                # 处理可能不完整的JSON字符串
                arguments = arguments.strip()
                if not arguments:
                    arguments = "{}"
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as e:
                    logger.warning(f"参数解析失败，尝试修复: {e}")
                    # 尝试修复缺失的大括号
                    if not arguments.startswith("{"):
                        arguments = "{" + arguments
                    if not arguments.endswith("}"):
                        arguments = arguments + "}"
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        # 最后的备用方案
                        arguments = {}
                        logger.error(f"无法解析参数，使用空参数: {function.get('arguments', '')}")
            elif not isinstance(arguments, dict):
                arguments = {}
            
            logger.info(f"执行工具: {function_name}, 参数: {arguments}")
            
            # 执行工具
            result = await mcp_manager.execute_tool(function_name, arguments)
            logger.info(result)
            # 添加工具结果消息（简化处理）
            request.messages.append(ChatMessage(
                role="tool",
                # content=json.dumps(result, ensure_ascii=False)
                content=f'{result}'
            ))
            
        except Exception as e:
            logger.error(f"工具执行失败: {function_name}, 错误: {e}")
            # 添加错误消息
            request.messages.append(ChatMessage(
                role="tool",
                content=json.dumps({"error": str(e)})
            ))
    
    def _build_system_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """构建系统提示"""
        tool_descriptions = []
        for tool in tools:
            func = tool["function"]
            name = func["name"]
            desc = func["description"]
            tool_descriptions.append(f"- {name}: {desc}")
        
        tools_text = "\n".join(tool_descriptions)
        
        return f"""你是一个智能助手，可以使用以下工具来帮助用户：

{tools_text}

使用工具时请：
1. 仔细分析用户需求
2. 选择合适的工具
3. 根据工具执行结果给出准确回答

请始终使用完整的工具名称（包含服务器前缀）。"""
