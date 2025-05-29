"""
会话管理插件 - 标准化版本
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from ..core.plugin import Plugin
from ..core.config import config
from ..core.models import ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """会话对象"""
    id: str
    created_at: datetime
    last_accessed: datetime
    messages: List[ChatMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True


class SessionManagerPlugin(Plugin):
    """会话管理插件"""

    def __init__(self, core):
        super().__init__(core)
        self.sessions: Dict[str, Session] = {}
        self.timeout: int = 3600  # 默认1小时超时
        self.max_active: int = 100  # 默认最大100个活跃会话
        self.cleanup_interval: int = 300  # 默认5分钟清理一次
        self.cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """初始化会话管理器"""
        # 从配置中读取参数
        self.timeout = config.get('session.timeout', 3600)
        self.max_active = config.get('session.max_active', 100)
        self.cleanup_interval = config.get('session.cleanup_interval', 300)

        logger.info(
            f"会话管理器初始化: timeout={self.timeout}s, max_active={self.max_active}, cleanup_interval={self.cleanup_interval}s")

        # 启动定期清理任务
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def shutdown(self):
        """插件关闭"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        # 清理所有会话
        self.sessions.clear()
        logger.info("会话管理器已关闭")

    def create_session(self, session_id: Optional[str] = None) -> Session:
        """创建新会话"""
        try:
            if session_id is None:
                session_id = str(uuid.uuid4())

            # 检查会话是否已存在
            if session_id in self.sessions:
                existing_session = self.sessions[session_id]
                if existing_session.active and not self._is_session_expired(existing_session):
                    logger.warning(f"会话 {session_id} 已存在，返回现有会话")
                    existing_session.last_accessed = datetime.now()
                    return existing_session

            # 检查活跃会话数量
            self._ensure_session_capacity()

            now = datetime.now()
            session = Session(
                id=session_id,
                created_at=now,
                last_accessed=now
            )

            self.sessions[session_id] = session
            logger.info(f"创建新会话: {session_id}")
            return session

        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            raise

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        try:
            session = self.sessions.get(session_id)
            if not session:
                return None

            # 检查是否过期
            if self._is_session_expired(session):
                session.active = False
                logger.info(f"会话 {session_id} 已过期")
                return None

            # 更新最后访问时间
            session.last_accessed = datetime.now()
            return session

        except Exception as e:
            logger.error(f"获取会话失败 {session_id}: {e}")
            return None

    def update_session(self, session_id: str, message: ChatMessage) -> bool:
        """更新会话消息"""
        try:
            session = self.get_session(session_id)
            if not session:
                logger.warning(f"更新会话失败，会话不存在: {session_id}")
                return False

            session.messages.append(message)
            session.last_accessed = datetime.now()
            logger.debug(f"更新会话 {session_id}，添加消息: {message.role}")
            return True

        except Exception as e:
            logger.error(f"更新会话失败 {session_id}: {e}")
            return False

    def get_session_messages(self, session_id: str, limit: Optional[int] = None) -> List[ChatMessage]:
        """获取会话消息历史"""
        try:
            session = self.get_session(session_id)
            if not session:
                return []

            messages = session.messages
            if limit and len(messages) > limit:
                messages = messages[-limit:]  # 返回最近的消息

            return messages

        except Exception as e:
            logger.error(f"获取会话消息失败 {session_id}: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        try:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"删除会话: {session_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"删除会话失败 {session_id}: {e}")
            return False

    def set_session_metadata(self, session_id: str, key: str, value: Any) -> bool:
        """设置会话元数据"""
        try:
            session = self.get_session(session_id)
            if not session:
                return False

            session.metadata[key] = value
            session.last_accessed = datetime.now()
            return True

        except Exception as e:
            logger.error(f"设置会话元数据失败 {session_id}: {e}")
            return False

    def get_session_metadata(self, session_id: str, key: str = None) -> Any:
        """获取会话元数据"""
        try:
            session = self.get_session(session_id)
            if not session:
                return None

            if key is None:
                return session.metadata
            return session.metadata.get(key)

        except Exception as e:
            logger.error(f"获取会话元数据失败 {session_id}: {e}")
            return None

    def cleanup_sessions(self) -> int:
        """清理过期会话"""
        try:
            expired_sessions = []
            for session_id, session in self.sessions.items():
                if self._is_session_expired(session):
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                self.delete_session(session_id)

            if expired_sessions:
                logger.info(f"清理了 {len(expired_sessions)} 个过期会话")

            return len(expired_sessions)

        except Exception as e:
            logger.error(f"清理会话失败: {e}")
            return 0

    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        try:
            active_count = sum(1 for s in self.sessions.values() if s.active and not self._is_session_expired(s))
            total_count = len(self.sessions)
            expired_count = sum(1 for s in self.sessions.values() if self._is_session_expired(s))

            return {
                "total_sessions": total_count,
                "active_sessions": active_count,
                "expired_sessions": expired_count,
                "max_active": self.max_active,
                "timeout": self.timeout
            }

        except Exception as e:
            logger.error(f"获取会话统计失败: {e}")
            return {}

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查清理任务是否正常运行
            if self.cleanup_task and self.cleanup_task.done():
                logger.warning("清理任务已停止，尝试重启")
                self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

            # 检查会话数量是否合理
            stats = self.get_session_stats()
            if stats.get("active_sessions", 0) > self.max_active * 1.1:  # 允许10%的缓冲
                logger.warning(f"活跃会话数量过多: {stats['active_sessions']}")
                return False

            return True

        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False

    def _is_session_expired(self, session: Session) -> bool:
        """检查会话是否过期"""
        if not session.active:
            return True

        expire_time = session.last_accessed + timedelta(seconds=self.timeout)
        return datetime.now() > expire_time

    def _ensure_session_capacity(self):
        """确保会话容量"""
        active_count = sum(1 for s in self.sessions.values() if s.active and not self._is_session_expired(s))

        if active_count >= self.max_active:
            # 先清理过期会话
            cleaned = self.cleanup_sessions()

            # 重新检查
            active_count = sum(1 for s in self.sessions.values() if s.active and not self._is_session_expired(s))
            if active_count >= self.max_active:
                # 清理最老的会话
                active_sessions = [s for s in self.sessions.values() if s.active and not self._is_session_expired(s)]
                if active_sessions:
                    oldest_session = min(active_sessions, key=lambda s: s.last_accessed)
                    oldest_session.active = False
                    logger.info(f"由于达到最大会话数，关闭会话: {oldest_session.id}")

    async def _periodic_cleanup(self):
        """定期清理任务"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                cleaned = self.cleanup_sessions()
                if cleaned > 0:
                    logger.debug(f"定期清理完成，清理了 {cleaned} 个会话")

            except asyncio.CancelledError:
                logger.info("定期清理任务已取消")
                break
            except Exception as e:
                logger.error(f"定期清理任务错误: {e}")
                # 继续运行，不退出循环