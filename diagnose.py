#!/usr/bin/env python3
"""
MCP Framework v2 问题诊断工具
"""
import json
import subprocess
import sys
import os
from pathlib import Path

def check_python_env():
    """检查Python环境"""
    print("🐍 检查Python环境...")
    print(f"Python版本: {sys.version}")
    
    # 检查必要的包
    required_packages = ['fastapi', 'uvicorn', 'pydantic', 'aiohttp', 'openai', 'mcp']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - 未安装")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n📦 请安装缺失的包: pip install {' '.join(missing_packages)}")
        return False
    return True

def check_config():
    """检查配置文件"""
    print("\n⚙️ 检查配置文件...")
    
    if not os.path.exists('config.json'):
        print("❌ 缺少config.json文件")
        return False
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # 检查必要的配置项
        required_keys = ['server', 'llm', 'mcp_servers']
        for key in required_keys:
            if key in config:
                print(f"✅ {key}")
            else:
                print(f"❌ 缺少配置项: {key}")
                return False
        
        # 检查服务器配置
        server = config.get('server', {})
        host = server.get('host', '0.0.0.0')
        port = server.get('port', 8000)
        print(f"📍 服务器配置: {host}:{port}")
        
        # 检查LLM配置
        llm = config.get('llm', {})
        base_url = llm.get('base_url', '')
        model = llm.get('model', '')
        print(f"🤖 LLM配置: {base_url} - {model}")
        
        # 检查MCP服务器
        mcp_servers = config.get('mcp_servers', [])
        enabled_servers = [s for s in mcp_servers if s.get('enabled', True)]
        print(f"🛠️ MCP服务器: {len(enabled_servers)} 个已启用")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件格式错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False

def check_mcp_tools():
    """检查MCP工具可用性"""
    print("\n🔧 检查MCP工具...")
    
    # 检查常用的MCP工具
    tools = [
        ('uvx', 'uvx --help'),
        ('npx', 'npx --version'),
        ('node', 'node --version'),
        ('npm', 'npm --version'),
    ]
    
    available_tools = []
    for tool_name, check_cmd in tools:
        try:
            result = subprocess.run(
                check_cmd.split(), 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                print(f"✅ {tool_name}")
                available_tools.append(tool_name)
            else:
                print(f"❌ {tool_name} - 不可用")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"❌ {tool_name} - 未找到")
    
    return len(available_tools) > 0

def check_ports():
    """检查端口占用"""
    print("\n🌐 检查端口占用...")
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(('localhost', 8000))
            if result == 0:
                print("⚠️ 端口8000已被占用")
                return False
            else:
                print("✅ 端口8000可用")
                return True
    except Exception as e:
        print(f"❌ 端口检查失败: {e}")
        return False

def generate_fix_suggestions():
    """生成修复建议"""
    print("\n🔧 修复建议:")
    print("1. 安装缺失的Python包: pip install -r requirements.txt")
    print("2. 检查config.json配置文件格式和内容")
    print("3. 确保Node.js和npm已安装（用于MCP服务器）")
    print("4. 检查LLM服务URL和API密钥是否正确")
    print("5. 如果端口被占用，修改config.json中的端口设置")
    print("6. 查看详细日志: python main.py")

def main():
    """主诊断流程"""
    print("🔍 MCP Framework v2 问题诊断工具")
    print("=" * 50)
    
    checks = [
        ("Python环境", check_python_env),
        ("配置文件", check_config), 
        ("MCP工具", check_mcp_tools),
        ("端口检查", check_ports),
    ]
    
    all_passed = True
    for name, check_func in checks:
        try:
            result = check_func()
            if not result:
                all_passed = False
        except Exception as e:
            print(f"❌ {name}检查失败: {e}")
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 所有检查通过！可以启动服务:")
        print("   python main.py")
        print("   或使用: bash start.sh")
    else:
        print("⚠️ 发现问题，请根据上述检查结果进行修复")
        generate_fix_suggestions()

if __name__ == "__main__":
    main()
