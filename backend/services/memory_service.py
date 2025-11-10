"""记忆服务：管理对话历史和邮件上下文记忆"""
from typing import List, Optional, Dict
from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain.memory.vectorstore import VectorStoreRetrieverMemory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from backend.config import settings
from backend.utils.logging_config import log
from backend.services.vector_store import VectorStoreService
from backend.db.models import Email


class MemoryService:
    """记忆服务类"""
    
    def __init__(self):
        self.vector_store_service = VectorStoreService()
        self.llm = None
        
        if settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0,
                api_key=settings.OPENAI_API_KEY
            )
    
    def create_buffer_memory(self, return_messages: bool = True) -> ConversationBufferMemory:
        """创建缓冲区记忆（存储最近对话）
        
        Args:
            return_messages: 是否返回消息对象
            
        Returns:
            ConversationBufferMemory实例
        """
        memory = ConversationBufferMemory(
            return_messages=return_messages,
            memory_key="chat_history"
        )
        return memory
    
    def create_summary_memory(self) -> ConversationSummaryMemory:
        """创建摘要记忆（自动总结旧上下文）
        
        Returns:
            ConversationSummaryMemory实例
        """
        if not self.llm:
            log.warning("LLM未初始化，无法创建摘要记忆")
            return self.create_buffer_memory()
        
        memory = ConversationSummaryMemory(
            llm=self.llm,
            return_messages=True,
            memory_key="chat_history"
        )
        return memory
    
    def create_vector_memory(self, k: int = 5) -> Optional[VectorStoreRetrieverMemory]:
        """创建向量记忆（基于向量存储的长期记忆）
        
        Args:
            k: 检索数量
            
        Returns:
            VectorStoreRetrieverMemory实例
        """
        if not self.vector_store_service.vector_store:
            log.warning("向量存储未初始化，无法创建向量记忆")
            return None
        
        try:
            retriever = self.vector_store_service.get_retriever(k=k)
            if not retriever:
                return None
            
            memory = VectorStoreRetrieverMemory(
                retriever=retriever,
                memory_key="history"
            )
            return memory
            
        except Exception as e:
            log.error(f"创建向量记忆失败: {e}", exc_info=True)
            return None
    
    def get_thread_memory(self, thread_id: str) -> ConversationBufferMemory:
        """获取邮件线程的记忆
        
        Args:
            thread_id: 邮件线程ID
            
        Returns:
            该线程的记忆对象
        """
        # 这里可以实现线程级别的记忆存储
        # 简化实现：为每个线程创建独立的记忆
        memory = self.create_buffer_memory()
        
        # TODO: 可以从数据库加载历史对话
        # 例如：从Email表中获取同一thread_id的邮件，构建对话历史
        
        return memory
    
    def add_email_to_memory(
        self,
        memory: ConversationBufferMemory,
        email: Email,
        response: Optional[str] = None
    ):
        """将邮件添加到记忆
        
        Args:
            memory: 记忆对象
            email: 邮件对象
            response: 回复内容（如果有）
        """
        try:
            # 构建邮件文本
            email_text = f"发件人: {email.sender_email}\n主题: {email.subject}\n正文: {email.body_text or email.body_html or ''}"
            
            # 添加为Human消息
            memory.chat_memory.add_user_message(email_text)
            
            # 如果有回复，添加为AI消息
            if response:
                memory.chat_memory.add_ai_message(response)
            
        except Exception as e:
            log.error(f"添加邮件到记忆失败: {e}", exc_info=True)
    
    def get_conversation_history(
        self,
        memory: ConversationBufferMemory,
        max_messages: int = 10
    ) -> List[BaseMessage]:
        """获取对话历史
        
        Args:
            memory: 记忆对象
            max_messages: 最大消息数
            
        Returns:
            消息列表
        """
        try:
            messages = memory.chat_memory.messages
            return messages[-max_messages:] if len(messages) > max_messages else messages
        except Exception as e:
            log.error(f"获取对话历史失败: {e}", exc_info=True)
            return []
    
    def clear_memory(self, memory: ConversationBufferMemory):
        """清空记忆
        
        Args:
            memory: 记忆对象
        """
        try:
            memory.clear()
            log.debug("记忆已清空")
        except Exception as e:
            log.error(f"清空记忆失败: {e}", exc_info=True)
    
    def build_context_from_thread(
        self,
        thread_id: str,
        db
    ) -> str:
        """从邮件线程构建上下文
        
        Args:
            thread_id: 线程ID
            db: 数据库会话
            
        Returns:
            上下文文本
        """
        try:
            # 获取同一线程的所有邮件
            from backend.db import crud
            emails = db.query(Email).filter(Email.thread_id == thread_id).order_by(Email.received_at).all()
            
            if not emails:
                return ""
            
            # 构建上下文
            context_parts = []
            for email in emails:
                context_parts.append(
                    f"[{email.received_at.strftime('%Y-%m-%d %H:%M') if email.received_at else '未知时间'}] "
                    f"{email.sender_email}: {email.subject}\n"
                    f"{email.body_text or email.body_html or ''}\n"
                )
            
            return "\n".join(context_parts)
            
        except Exception as e:
            log.error(f"构建线程上下文失败: {e}", exc_info=True)
            return ""

