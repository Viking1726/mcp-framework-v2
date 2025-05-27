"""
应用层 - 应用服务和用例编排

处理命令、查询和应用逻辑
"""

from typing import List, Optional, Dict, Any, AsyncIterator
from dataclasses import dataclass
from abc import ABC, abstractmethod

from core.domain import (
    Conversation, Message, MessageId, SessionId, MessageRole,
    ToolCall, ToolCallId, ToolCallStatus,
    ConversationRepository, ToolExecutor, MessageValidator, LLMClient
)


# 命令定义
@dataclass
class Command(ABC):
    """命令基类"""
    pass


@dataclass
class StartConversationCommand(Command):
    """开始对话命令"""
    session_id: Optional[SessionId] = None


@dataclass
class SendMessageCommand(Command):
    """发送消息命令"""
    session_id: SessionId
    content: str
    role: MessageRole = MessageRole.USER
    name: Optional[str] = None


@dataclass
class ExecuteToolCallsCommand(Command):
    """执行工具调用命令"""
    session_id: SessionId
    tool_calls: List[Dict[str, Any]]


@dataclass
class ChatCompletionCommand(Command):
    """聊天完成命令"""
    session_id: SessionId
    messages: List[Message]
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None


# 查询定义
@dataclass
class Query(ABC):
    """查询基类"""
    pass


@dataclass
class GetConversationQuery(Query):
    """获取对话查询"""
    session_id: SessionId


@dataclass
class ListActiveConversationsQuery(Query):
    """列出活跃对话查询"""
    limit: int = 100


@dataclass
class GetAvailableToolsQuery(Query):
    """获取可用工具查询"""
    pass


# 结果定义
@dataclass
class ConversationResult:
    """对话结果"""
    session_id: SessionId
    messages: List[Message]
    tool_calls: Dict[str, ToolCall]


@dataclass
class ChatCompletionResult:
    """聊天完成结果"""
    session_id: SessionId
    response_message: Message
    tool_calls: List[ToolCall]


@dataclass
class StreamingChatResult:
    """流式聊天结果"""
    session_id: SessionId
    chunks: AsyncIterator[Dict[str, Any]]


# 命令处理器
class ConversationCommandHandler:
    """对话命令处理器"""
    
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        tool_executor: ToolExecutor,
        message_validator: MessageValidator,
        llm_client: LLMClient
    ):
        self._conversation_repo = conversation_repo
        self._tool_executor = tool_executor
        self._message_validator = message_validator
        self._llm_client = llm_client
    
    async def handle_start_conversation(self, command: StartConversationCommand) -> ConversationResult:
        """处理开始对话命令"""
        session_id = command.session_id or SessionId()
        
        # 检查是否已存在对话
        existing_conversation = await self._conversation_repo.find_by_id(session_id)
        if existing_conversation:
            return ConversationResult(
                session_id=session_id,
                messages=existing_conversation.messages,
                tool_calls=existing_conversation.tool_calls
            )
        
        # 创建新对话
        conversation = Conversation(session_id)
        await self._conversation_repo.save(conversation)
        
        return ConversationResult(
            session_id=session_id,
            messages=[],
            tool_calls={}
        )
    
    async def handle_send_message(self, command: SendMessageCommand) -> ConversationResult:
        """处理发送消息命令"""
        # 获取对话
        conversation = await self._conversation_repo.find_by_id(command.session_id)
        if not conversation:
            # 如果对话不存在，创建新对话
            start_command = StartConversationCommand(session_id=command.session_id)
            await self.handle_start_conversation(start_command)
            conversation = await self._conversation_repo.find_by_id(command.session_id)
        
        # 添加用户消息
        user_message = Message(
            id=MessageId(),
            role=command.role,
            content=command.content,
            name=command.name
        )
        conversation.add_message(user_message)
        
        # 保存对话
        await self._conversation_repo.save(conversation)
        
        return ConversationResult(
            session_id=command.session_id,
            messages=conversation.messages,
            tool_calls=conversation.tool_calls
        )
    
    async def handle_execute_tool_calls(self, command: ExecuteToolCallsCommand) -> ConversationResult:
        """处理执行工具调用命令"""
        conversation = await self._conversation_repo.find_by_id(command.session_id)
        if not conversation:
            raise ValueError(f"Conversation {command.session_id.value} not found")
        
        # 创建工具调用对象
        tool_calls = []
        for tool_call_data in command.tool_calls:
            tool_call = ToolCall(
                id=ToolCallId(tool_call_data.get('id', f"call_{len(tool_calls)}")),
                function_name=tool_call_data.get('function', {}).get('name', ''),
                arguments=tool_call_data.get('function', {}).get('arguments', {})
            )
            tool_calls.append(tool_call)
        
        # 执行工具调用
        completed_tool_calls = []
        for tool_call in tool_calls:
            try:
                # 更新状态为执行中
                executing_tool_call = tool_call.with_status(ToolCallStatus.EXECUTING)
                conversation.update_tool_call(tool_call.id.value, executing_tool_call)
                
                # 执行工具
                completed_tool_call = await self._tool_executor.execute_tool(tool_call)
                conversation.update_tool_call(tool_call.id.value, completed_tool_call)
                completed_tool_calls.append(completed_tool_call)
                
            except Exception as e:
                # 执行失败
                failed_tool_call = tool_call.with_error(str(e))
                conversation.update_tool_call(tool_call.id.value, failed_tool_call)
                completed_tool_calls.append(failed_tool_call)
        
        # 保存对话
        await self._conversation_repo.save(conversation)
        
        return ConversationResult(
            session_id=command.session_id,
            messages=conversation.messages,
            tool_calls=conversation.tool_calls
        )
    
    async def handle_chat_completion(self, command: ChatCompletionCommand) -> StreamingChatResult:
        """处理聊天完成命令"""
        conversation = await self._conversation_repo.find_by_id(command.session_id)
        if not conversation:
            raise ValueError(f"Conversation {command.session_id.value} not found")
        
        # 验证并修复消息序列
        validated_messages = self._message_validator.fix_incomplete_sequence(command.messages)
        
        # 创建流式响应生成器
        async def generate_completion():
            try:
                # 调用LLM完成聊天
                async for chunk in self._llm_client.complete_chat(
                    messages=validated_messages,
                    model=command.model,
                    temperature=command.temperature,
                    max_tokens=command.max_tokens,
                    tools=command.tools,
                    tool_choice=command.tool_choice
                ):
                    yield chunk
                    
                    # 如果包含工具调用，处理工具执行
                    if self._should_execute_tools(chunk):
                        tool_calls = self._extract_tool_calls(chunk)
                        if tool_calls:
                            # 执行工具调用
                            execute_command = ExecuteToolCallsCommand(
                                session_id=command.session_id,
                                tool_calls=tool_calls
                            )
                            await self.handle_execute_tool_calls(execute_command)
                            
                            # 生成工具执行结果的响应块
                            yield self._create_tool_execution_chunk(tool_calls)
            
            except Exception as e:
                # 生成错误响应块
                yield self._create_error_chunk(str(e))
        
        return StreamingChatResult(
            session_id=command.session_id,
            chunks=generate_completion()
        )
    
    def _should_execute_tools(self, chunk: Dict[str, Any]) -> bool:
        """判断是否应该执行工具"""
        choices = chunk.get('choices', [])
        if not choices:
            return False
        
        choice = choices[0]
        finish_reason = choice.get('finish_reason')
        return finish_reason == 'tool_calls'
    
    def _extract_tool_calls(self, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从响应块中提取工具调用"""
        choices = chunk.get('choices', [])
        if not choices:
            return []
        
        choice = choices[0]
        delta = choice.get('delta', {})
        return delta.get('tool_calls', [])
    
    def _create_tool_execution_chunk(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """创建工具执行响应块"""
        return {
            "choices": [{
                "delta": {"content": f"\n[执行了 {len(tool_calls)} 个工具]\n"},
                "index": 0,
                "finish_reason": None
            }],
            "object": "chat.completion.chunk"
        }
    
    def _create_error_chunk(self, error_message: str) -> Dict[str, Any]:
        """创建错误响应块"""
        return {
            "choices": [{
                "delta": {"content": f"\n[错误: {error_message}]\n"},
                "index": 0,
                "finish_reason": "error"
            }],
            "object": "chat.completion.chunk"
        }


# 查询处理器
class ConversationQueryHandler:
    """对话查询处理器"""
    
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        tool_executor: ToolExecutor
    ):
        self._conversation_repo = conversation_repo
        self._tool_executor = tool_executor
    
    async def handle_get_conversation(self, query: GetConversationQuery) -> Optional[ConversationResult]:
        """处理获取对话查询"""
        conversation = await self._conversation_repo.find_by_id(query.session_id)
        if not conversation:
            return None
        
        return ConversationResult(
            session_id=query.session_id,
            messages=conversation.messages,
            tool_calls=conversation.tool_calls
        )
    
    async def handle_list_active_conversations(self, query: ListActiveConversationsQuery) -> List[ConversationResult]:
        """处理列出活跃对话查询"""
        conversations = await self._conversation_repo.find_active_conversations(query.limit)
        
        results = []
        for conversation in conversations:
            results.append(ConversationResult(
                session_id=conversation.id,
                messages=conversation.messages,
                tool_calls=conversation.tool_calls
            ))
        
        return results
    
    async def handle_get_available_tools(self, query: GetAvailableToolsQuery) -> List[Dict[str, Any]]:
        """处理获取可用工具查询"""
        return await self._tool_executor.get_available_tools()


# 应用服务门面
class ConversationApplicationService:
    """对话应用服务"""
    
    def __init__(
        self,
        command_handler: ConversationCommandHandler,
        query_handler: ConversationQueryHandler
    ):
        self._command_handler = command_handler
        self._query_handler = query_handler
    
    # 命令方法
    async def start_conversation(self, session_id: Optional[SessionId] = None) -> ConversationResult:
        """开始对话"""
        command = StartConversationCommand(session_id=session_id)
        return await self._command_handler.handle_start_conversation(command)
    
    async def send_message(
        self, 
        session_id: SessionId, 
        content: str, 
        role: MessageRole = MessageRole.USER,
        name: Optional[str] = None
    ) -> ConversationResult:
        """发送消息"""
        command = SendMessageCommand(
            session_id=session_id,
            content=content,
            role=role,
            name=name
        )
        return await self._command_handler.handle_send_message(command)
    
    async def execute_tool_calls(
        self, 
        session_id: SessionId, 
        tool_calls: List[Dict[str, Any]]
    ) -> ConversationResult:
        """执行工具调用"""
        command = ExecuteToolCallsCommand(
            session_id=session_id,
            tool_calls=tool_calls
        )
        return await self._command_handler.handle_execute_tool_calls(command)
    
    async def complete_chat(
        self,
        session_id: SessionId,
        messages: List[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None
    ) -> StreamingChatResult:
        """完成聊天"""
        command = ChatCompletionCommand(
            session_id=session_id,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice
        )
        return await self._command_handler.handle_chat_completion(command)
    
    # 查询方法
    async def get_conversation(self, session_id: SessionId) -> Optional[ConversationResult]:
        """获取对话"""
        query = GetConversationQuery(session_id=session_id)
        return await self._query_handler.handle_get_conversation(query)
    
    async def list_active_conversations(self, limit: int = 100) -> List[ConversationResult]:
        """列出活跃对话"""
        query = ListActiveConversationsQuery(limit=limit)
        return await self._query_handler.handle_list_active_conversations(query)
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具"""
        query = GetAvailableToolsQuery()
        return await self._query_handler.handle_get_available_tools(query)
