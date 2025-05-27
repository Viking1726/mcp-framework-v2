"""
MCP管理器插件 - 精简版
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..core.plugin import Plugin
from ..core.config import config

logger = logging.getLogger(__name__)

class MCPManagerPlugin(Plugin):
    """MCP管理器插件"""
    
    def __init__(self, core):
        super().__init__(core)
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.exit_stack = AsyncExitStack()
        
    async def initialize(self):
        """初始化MCP服务器"""
        logger.info("初始化MCP管理器...")
        
        # 启动配置的服务器
        servers_config = config.get('mcp_servers', [])
        for server_config in servers_config:
            if server_config.get('enabled', True):
                await self._start_server(server_config)
    
    async def _start_server(self, server_config: Dict[str, Any]) -> bool:
        """启动单个MCP服务器"""
        server_id = server_config['id']
        
        try:
            logger.info(f"启动MCP服务器: {server_id}")
            
            # 创建服务器参数
            params = StdioServerParameters(
                command=server_config['command'],
                args=server_config.get('args', []),
                env=server_config.get('env')
            )
            
            # 建立连接
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(params)
            )
            stdio, write = stdio_transport
            
            # 创建会话
            session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            
            # 初始化
            await asyncio.wait_for(session.initialize(), timeout=30)
            
            # 获取工具列表
            tools_response = await asyncio.wait_for(session.list_tools(), timeout=10)
            tools = tools_response.tools
            
            # 存储服务器信息
            self.servers[server_id] = {
                'session': session,
                'tools': tools,
                'config': server_config
            }
            
            logger.info(f"服务器 {server_id} 启动成功，工具数: {len(tools)}")
            return True
            
        except Exception as e:
            logger.error(f"启动服务器 {server_id} 失败: {e}")
            return False
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有工具（OpenAI格式）"""
        tools = []
        
        for server_id, server_info in self.servers.items():
            for tool in server_info['tools']:
                # 转换为OpenAI工具格式
                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": f"{server_id}_{tool.name}",
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                }
                tools.append(openai_tool)
        
        return tools
    
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具"""
        # 解析工具名称 (server_id_tool_name)
        server_id, actual_tool_name = self._parse_tool_name(tool_name)
        
        if server_id not in self.servers:
            raise ValueError(f"服务器 {server_id} 不存在")
        
        server_info = self.servers[server_id]
        session = server_info['session']
        
        try:
            # 执行工具调用
            result = await asyncio.wait_for(
                session.call_tool(actual_tool_name, arguments),
                timeout=300
            )
            return result.content
            
        except Exception as e:
            logger.error(f"工具执行失败: {tool_name}, 错误: {e}")
            return {"error": str(e)}
    
    def _parse_tool_name(self, tool_name: str) -> Tuple[str, str]:
        """解析工具名称"""
        if '_' in tool_name:
            parts = tool_name.split('_', 1)
            return parts[0], parts[1]
        else:
            # 如果没有前缀，尝试在所有服务器中查找
            for server_id, server_info in self.servers.items():
                for tool in server_info['tools']:
                    if tool.name == tool_name:
                        return server_id, tool_name
        
        raise ValueError(f"无法解析工具名称: {tool_name}")
    
    async def shutdown(self):
        """关闭所有服务器"""
        logger.info("关闭MCP管理器...")
        await self.exit_stack.aclose()
