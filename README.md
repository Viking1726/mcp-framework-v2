# MCP Framework v2 - 微核心架构

## 概述

这是MCP Framework的v2版本，采用微核心+插件的架构设计，相比v1版本：

- **代码量减少40%+**
- **架构更清晰**：核心框架 + 功能插件
- **配置更简单**：单一JSON文件驱动
- **扩展更容易**：插件式设计

## 架构特点

### 微核心设计
- **Core模块**：配置管理、应用框架、插件系统
- **Plugin模块**：LLM客户端、MCP管理器、聊天处理器
- **配置驱动**：所有行为由config.json控制

### 核心优化
1. **统一配置管理**：一个Config类处理所有配置
2. **插件化架构**：功能模块化，松耦合设计  
3. **简化错误处理**：统一的异常处理策略
4. **精简数据模型**：只保留必要的数据结构

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置文件
编辑 `config.json`：
```json
{
  "server": {"host": "0.0.0.0", "port": 8000},
  "llm": {
    "base_url": "你的LLM服务URL",
    "api_key": "你的API密钥",
    "model": "模型名称"
  },
  "mcp_servers": [
    {
      "id": "time",
      "command": "uvx",
      "args": ["mcp-server-time"],
      "enabled": true
    }
  ]
}
```

### 3. 启动服务
```bash
python main.py
```

## API使用

与OpenAI API完全兼容：

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "现在几点？"}],
    stream=True
)
```

## 插件开发

### 创建新插件

```python
from src.core.plugin import Plugin

class MyPlugin(Plugin):
    async def initialize(self):
        # 初始化逻辑
        pass
    
    async def shutdown(self):
        # 清理逻辑
        pass
```

### 注册插件
在 `src/core/app.py` 的 `_load_plugins` 方法中添加：

```python
("my_plugin", MyPlugin),
```

## 目录结构

```
mcp-framework-v2/
├── config.json          # 配置文件
├── main.py             # 启动入口
├── requirements.txt    # 依赖列表
└── src/
    ├── core/           # 核心框架
    │   ├── app.py      # 应用框架
    │   ├── config.py   # 配置管理
    │   ├── models.py   # 数据模型
    │   └── plugin.py   # 插件基类
    └── plugins/        # 功能插件
        ├── llm_client.py      # LLM客户端
        ├── mcp_manager.py     # MCP管理器
        └── chat_handler.py    # 聊天处理器
```

## 对比v1版本

| 特性 | v1版本 | v2版本 |
|------|--------|--------|
| 代码行数 | ~2000行 | ~1200行 |
| 文件数量 | 10个文件 | 8个文件 |
| 配置复杂度 | 多个配置类 | 单一配置管理 |
| 扩展难度 | 需要修改核心 | 添加插件即可 |
| 启动时间 | 较慢 | 更快 |

## 支持的功能

- ✅ OpenAI API兼容
- ✅ 多种LLM服务支持
- ✅ MCP工具集成
- ✅ 交互式工具调用
- ✅ 流式响应
- ✅ 健康检查
- ✅ 插件式架构

## 注意事项

1. **配置文件**：请根据实际情况修改config.json
2. **MCP服务器**：确保系统已安装相应的MCP服务器
3. **API密钥**：请设置正确的LLM服务API密钥
