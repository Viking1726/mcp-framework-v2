"""
精简数据模型
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

class ToolMessage(BaseModel):
    """聊天消息"""
    role: str
    tool_call_id: str
    content: Optional[str] = None

class ChatRequest(BaseModel):
    """聊天请求"""
    session_id: str
    model: str
    messages: List[ChatMessage]
    stream: bool = True
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: str = "auto"
    temperature: float = 0.7
    max_tokens: Optional[int] = None

class ChatResponse(BaseModel):
    """聊天响应"""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]

class ModelObject(BaseModel):
    """模型对象格式"""
    id: str
    object: str = "model"
    created: int
    owned_by: str

class ModelListResponse(BaseModel):
    """模型列表响应格式"""
    object: str = "list"
    data: List[ModelObject]


