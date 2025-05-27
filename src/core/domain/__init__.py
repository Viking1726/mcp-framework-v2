"""
领域层 - 核心业务逻辑

包含实体、值对象、仓储接口和领域服务
"""

from typing import Protocol, TypeVar, Generic, Optional, List, Dict, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

# 基础类型定义
EntityId = TypeVar('EntityId')
T = TypeVar('T')


class Entity(Generic[EntityId], ABC):
    """领域实体基类"""
    
    def __init__(self, id: EntityId):
        self._id = id
        self._created_at = datetime.utcnow()
        self._updated_at = datetime.utcnow()
    
    @property
    def id(self) -> EntityId:
        return self._id
    
    @property
    def created_at(self) -> datetime:
        return self._created_at
    
    @property
    def updated_at(self) -> datetime:
        return self._updated_at
    
    def _update_timestamp(self):
        self._updated_at = datetime.utcnow()
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Entity):
            return False
        return self._id == other._id
    
    def __hash__(self) -> int:
        return hash(self._id)


@dataclass(frozen=True)
class ValueObject:
    """值对象基类"""
    pass


class MessageRole(Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolCallStatus(Enum):
    """工具调用状态"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class MessageId(ValueObject):
    """消息ID值对象"""
    value: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class SessionId(ValueObject):
    """会话ID值对象"""
    value: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class ToolCallId(ValueObject):
    """工具调用ID值对象"""
    value: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")


@dataclass(frozen=True)
class Message(ValueObject):
    """消息值对象"""
    id: MessageId
    role: MessageRole
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    
    def is_tool_call_message(self) -> bool:
        """判断是否为工具调用消息"""
        return self.role == MessageRole.ASSISTANT and self.tool_calls is not None
    
    def is_tool_response_message(self) -> bool:
        """判断是否为工具响应消息"""
        return self.role == MessageRole.TOOL and self.tool_call_id is not None


@dataclass(frozen=True)
class ToolCall(ValueObject):
    """工具调用值对象"""
    id: ToolCallId
    function_name: str
    arguments: Dict[str, Any]
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def with_status(self, status: ToolCallStatus) -> 'ToolCall':
        """返回带有新状态的工具调用"""
        kwargs = {
            'id': self.id,
            'function_name': self.function_name,
            'arguments': self.arguments,
            'status': status,
            'result': self.result,
            'error': self.error,
            'started_at': self.started_at if status != ToolCallStatus.EXECUTING else datetime.utcnow(),
            'completed_at': self.completed_at if status not in [ToolCallStatus.COMPLETED, ToolCallStatus.FAILED] else datetime.utcnow()
        }
        return ToolCall(**kwargs)
    
    def with_result(self, result: Any) -> 'ToolCall':
        """返回带有结果的工具调用"""
        return self.with_status(ToolCallStatus.COMPLETED).replace(result=result)
    
    def with_error(self, error: str) -> 'ToolCall':
        """返回带有错误的工具调用"""
        return self.with_status(ToolCallStatus.FAILED).replace(error=error)


class Conversation(Entity[SessionId]):
    """对话聚合根"""
    
    def __init__(self, session_id: SessionId):
        super().__init__(session_id)
        self._messages: List[Message] = []
        self._tool_calls: Dict[str, ToolCall] = {}
        self._context_data: Dict[str, Any] = {}
    
    @property
    def messages(self) -> List[Message]:
        """获取消息列表"""
        return self._messages.copy()
    
    @property
    def tool_calls(self) -> Dict[str, ToolCall]:
        """获取工具调用映射"""
        return self._tool_calls.copy()
    
    def add_message(self, message: Message) -> None:
        """添加消息"""
        # 验证消息序列的完整性
        if message.is_tool_call_message():
            # 记录工具调用
            if message.tool_calls:
                for tool_call_data in message.tool_calls:
                    tool_call_id = tool_call_data.get('id')
                    if tool_call_id:
                        tool_call = ToolCall(
                            id=ToolCallId(tool_call_id),
                            function_name=tool_call_data.get('function', {}).get('name', ''),
                            arguments=tool_call_data.get('function', {}).get('arguments', {}),
                        )
                        self._tool_calls[tool_call_id] = tool_call
        
        elif message.is_tool_response_message():
            # 验证工具响应对应的调用是否存在
            if message.tool_call_id not in self._tool_calls:
                raise ValueError(f"Tool call {message.tool_call_id} not found")
        
        self._messages.append(message)
        self._update_timestamp()
    
    def update_tool_call(self, tool_call_id: str, tool_call: ToolCall) -> None:
        """更新工具调用状态"""
        if tool_call_id not in self._tool_calls:
            raise ValueError(f"Tool call {tool_call_id} not found")
        
        self._tool_calls[tool_call_id] = tool_call
        self._update_timestamp()
    
    def get_pending_tool_calls(self) -> List[ToolCall]:
        """获取待执行的工具调用"""
        return [tc for tc in self._tool_calls.values() if tc.status == ToolCallStatus.PENDING]
    
    def validate_message_sequence(self) -> bool:
        """验证消息序列的完整性"""
        # 检查每个工具调用是否都有对应的响应
        for message in self._messages:
            if message.is_tool_call_message() and message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_call_id = tool_call.get('id')
                    if tool_call_id:
                        # 查找对应的工具响应消息
                        has_response = any(
                            m.is_tool_response_message() and m.tool_call_id == tool_call_id
                            for m in self._messages
                        )
                        if not has_response:
                            return False
        return True
    
    def set_context_data(self, key: str, value: Any) -> None:
        """设置上下文数据"""
        self._context_data[key] = value
        self._update_timestamp()
    
    def get_context_data(self, key: str) -> Optional[Any]:
        """获取上下文数据"""
        return self._context_data.get(key)


# 仓储接口
class Repository(Generic[T, EntityId], Protocol):
    """仓储基础接口"""
    
    @abstractmethod
    async def save(self, entity: T) -> None:
        """保存实体"""
        pass
    
    @abstractmethod
    async def find_by_id(self, id: EntityId) -> Optional[T]:
        """根据ID查找实体"""
        pass
    
    @abstractmethod
    async def delete(self, id: EntityId) -> bool:
        """删除实体"""
        pass


class ConversationRepository(Repository[Conversation, SessionId], Protocol):
    """对话仓储接口"""
    
    @abstractmethod
    async def find_active_conversations(self, limit: int = 100) -> List[Conversation]:
        """查找活跃的对话"""
        pass
    
    @abstractmethod
    async def cleanup_expired_conversations(self, ttl_seconds: int) -> int:
        """清理过期的对话"""
        pass


# 领域服务接口
class ToolExecutor(Protocol):
    """工具执行器接口"""
    
    @abstractmethod
    async def execute_tool(self, tool_call: ToolCall) -> ToolCall:
        """执行工具调用"""
        pass
    
    @abstractmethod
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        pass


class MessageValidator(Protocol):
    """消息验证器接口"""
    
    @abstractmethod
    def validate_message_sequence(self, messages: List[Message]) -> bool:
        """验证消息序列"""
        pass
    
    @abstractmethod
    def fix_incomplete_sequence(self, messages: List[Message]) -> List[Message]:
        """修复不完整的消息序列"""
        pass


class LLMClient(Protocol):
    """LLM客户端接口"""
    
    @abstractmethod
    async def complete_chat(self, messages: List[Message], **kwargs) -> Any:
        """完成聊天"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
