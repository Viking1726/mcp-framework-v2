#!/usr/bin/env python3
"""
MCP Framework v2 启动器 - 微核心架构
"""
import os
import sys
import logging
import uvicorn

# 添加src到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def setup_logging():
    """设置日志"""
    from src.core.config import config
    
    level = getattr(logging, config.get('logging.level', 'INFO').upper())
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )

def main():
    """主函数"""
    try:
        # 设置日志
        setup_logging()
        
        # 导入核心应用
        from src.core.app import core
        from src.core.config import config
        
        logger = logging.getLogger(__name__)
        logger.info("启动MCP Framework v2 - 微核心架构")
        
        # 获取服务器配置  
        host = config.get('server.host', '0.0.0.0')
        port = config.get('server.port', 8000)
        
        logger.info(f"服务器地址: {host}:{port}")
        logger.info(f"LLM服务: {config.get('llm.base_url')}")
        
        # 启动服务器
        uvicorn.run(
            core.app,
            host=host,
            port=port,
            log_level="info"
        )
        
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
