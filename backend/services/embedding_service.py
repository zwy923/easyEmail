"""向量化服务：将邮件文本转换为向量"""
from typing import List, Optional
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from backend.config import settings
from backend.utils.logging_config import log
from backend.db.models import Email


class EmbeddingService:
    """向量化服务类"""
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            log.warning("OpenAI API密钥未配置，无法生成向量")
            self.embeddings = None
        else:
            self.embeddings = OpenAIEmbeddings(
                openai_api_key=settings.OPENAI_API_KEY,
                model=settings.EMBEDDING_MODEL  # 使用配置的模型
            )
    
    def embed_email(self, email: Email) -> Optional[List[float]]:
        """将邮件转换为向量
        
        Args:
            email: 邮件对象
            
        Returns:
            向量列表，如果失败返回None
        """
        if not self.embeddings:
            return None
        
        try:
            # 构建邮件文本
            text = self._build_email_text(email)
            
            # 生成向量
            vector = self.embeddings.embed_query(text)
            
            log.debug(f"邮件 {email.id} 向量化成功，维度: {len(vector)}")
            return vector
            
        except Exception as e:
            log.error(f"邮件 {email.id} 向量化失败: {e}", exc_info=True)
            return None
    
    def embed_emails_batch(self, emails: List[Email]) -> List[Optional[List[float]]]:
        """批量向量化邮件
        
        Args:
            emails: 邮件对象列表
            
        Returns:
            向量列表，失败项为None
        """
        if not self.embeddings:
            return [None] * len(emails)
        
        try:
            # 构建文本列表
            texts = [self._build_email_text(email) for email in emails]
            
            # 批量生成向量
            vectors = self.embeddings.embed_documents(texts)
            
            log.info(f"批量向量化 {len(emails)} 封邮件成功")
            return vectors
            
        except Exception as e:
            log.error(f"批量向量化失败: {e}", exc_info=True)
            return [None] * len(emails)
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """将文本转换为向量
        
        Args:
            text: 文本内容
            
        Returns:
            向量列表，如果失败返回None
        """
        if not self.embeddings:
            return None
        
        try:
            vector = self.embeddings.embed_query(text)
            return vector
        except Exception as e:
            log.error(f"文本向量化失败: {e}", exc_info=True)
            return None
    
    def _build_email_text(self, email: Email) -> str:
        """构建邮件文本（用于向量化）
        
        Args:
            email: 邮件对象
            
        Returns:
            组合后的文本
        """
        parts = []
        
        if email.subject:
            parts.append(f"主题: {email.subject}")
        
        if email.sender or email.sender_email:
            parts.append(f"发件人: {email.sender or email.sender_email}")
        
        if email.body_text:
            parts.append(f"正文: {email.body_text[:2000]}")  # 限制长度
        elif email.body_html:
            # 简单提取HTML文本（实际应该使用更复杂的HTML解析）
            parts.append(f"正文: {email.body_html[:2000]}")
        
        return "\n".join(parts)
    
    def create_document(self, email: Email) -> Optional[Document]:
        """创建LangChain Document对象
        
        Args:
            email: 邮件对象
            
        Returns:
            Document对象，包含文本和元数据
        """
        text = self._build_email_text(email)
        
        metadata = {
            "email_id": email.id,
            "subject": email.subject,
            "sender": email.sender_email,
            "received_at": email.received_at.isoformat() if email.received_at else None,
            "category": email.category.value if email.category else None
        }
        
        return Document(page_content=text, metadata=metadata)

