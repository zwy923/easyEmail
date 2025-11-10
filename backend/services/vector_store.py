"""向量存储服务：使用PGVector存储和检索邮件向量"""
from typing import List, Optional, Dict
try:
    from langchain_community.vectorstores import PGVector
except ImportError:
    # 兼容旧版本
    try:
        from langchain.vectorstores import PGVector
    except ImportError:
        from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.documents import Document
from sqlalchemy.orm import Session

from backend.config import settings
from backend.utils.logging_config import log
from backend.services.embedding_service import EmbeddingService
from backend.db.models import Email
from backend.db import crud


class VectorStoreService:
    """向量存储服务类"""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.connection_string = self._build_connection_string()
        self.vector_store = None
        self._initialize_store()
    
    def _build_connection_string(self) -> str:
        """构建PGVector连接字符串"""
        # 从DATABASE_URL提取连接信息
        db_url = settings.DATABASE_URL
        # PGVector需要特定的连接格式
        return db_url
    
    def _initialize_store(self):
        """初始化向量存储"""
        if not self.embedding_service.embeddings:
            log.warning("向量化服务未初始化，无法创建向量存储")
            return
        
        try:
            # 创建或加载PGVector存储
            self.vector_store = PGVector(
                connection_string=self.connection_string,
                embedding_function=self.embedding_service.embeddings,
                collection_name=settings.COLLECTION_NAME
            )
            log.info("向量存储初始化成功")
        except Exception as e:
            log.error(f"向量存储初始化失败: {e}", exc_info=True)
            self.vector_store = None
    
    def add_email(self, email: Email) -> bool:
        """添加邮件到向量存储
        
        Args:
            email: 邮件对象
            
        Returns:
            是否成功
        """
        if not self.vector_store:
            return False
        
        try:
            # 创建Document对象
            doc = self.embedding_service.create_document(email)
            if not doc:
                return False
            
            # 添加到向量存储
            self.vector_store.add_documents([doc], ids=[str(email.id)])
            
            log.info(f"邮件 {email.id} 已添加到向量存储")
            return True
            
        except Exception as e:
            log.error(f"添加邮件到向量存储失败: {e}", exc_info=True)
            return False
    
    def add_emails_batch(self, emails: List[Email]) -> int:
        """批量添加邮件到向量存储
        
        Args:
            emails: 邮件对象列表
            
        Returns:
            成功添加的数量
        """
        if not self.vector_store:
            return 0
        
        try:
            # 创建Document对象列表
            docs = []
            ids = []
            for email in emails:
                doc = self.embedding_service.create_document(email)
                if doc:
                    docs.append(doc)
                    ids.append(str(email.id))
            
            if not docs:
                return 0
            
            # 批量添加
            self.vector_store.add_documents(docs, ids=ids)
            
            log.info(f"批量添加 {len(docs)} 封邮件到向量存储")
            return len(docs)
            
        except Exception as e:
            log.error(f"批量添加邮件到向量存储失败: {e}", exc_info=True)
            return 0
    
    def search_similar_emails(
        self,
        query: str,
        k: int = None,
        filter_dict: Optional[Dict] = None
    ) -> List[Document]:
        """搜索相似邮件
        
        Args:
            query: 查询文本
            k: 返回数量（默认使用配置值）
            filter_dict: 过滤条件（元数据过滤）
            
        Returns:
            相似邮件Document列表
        """
        if not self.vector_store:
            return []
        
        try:
            k = k or settings.RAG_TOP_K
            
            # 执行相似度搜索
            if filter_dict:
                results = self.vector_store.similarity_search_with_score(
                    query,
                    k=k,
                    filter=filter_dict
                )
            else:
                results = self.vector_store.similarity_search_with_score(query, k=k)
            
            # 提取Document（去掉score）
            documents = [doc for doc, score in results]
            
            log.debug(f"搜索相似邮件，查询: {query[:50]}..., 返回: {len(documents)} 条结果")
            return documents
            
        except Exception as e:
            log.error(f"搜索相似邮件失败: {e}", exc_info=True)
            return []
    
    def get_email_context(
        self,
        email: Email,
        k: int = None
    ) -> List[Document]:
        """获取邮件的上下文（相似邮件）
        
        Args:
            email: 邮件对象
            k: 返回数量
            
        Returns:
            相似邮件Document列表
        """
        if not self.vector_store:
            return []
        
        # 构建查询文本
        query_text = self.embedding_service._build_email_text(email)
        
        # 搜索相似邮件（排除自己）
        # 注意：PGVector的filter语法可能不同，先搜索更多结果然后过滤
        search_k = (k or settings.RAG_TOP_K) + 1
        results = self.search_similar_emails(query_text, k=search_k)
        
        # 过滤掉当前邮件
        filtered_results = [
            doc for doc in results
            if doc.metadata.get("email_id") != email.id
        ]
        
        # 返回指定数量
        return filtered_results[:k] if k else filtered_results[:settings.RAG_TOP_K]
    
    def update_email(self, email: Email) -> bool:
        """更新邮件向量（先删除再添加）
        
        Args:
            email: 邮件对象
            
        Returns:
            是否成功
        """
        if not self.vector_store:
            return False
        
        try:
            # 先删除旧的向量
            self.delete_email(email.id)
            
            # 重新添加（使用相同的ID会覆盖）
            return self.add_email(email)
            
        except Exception as e:
            log.error(f"更新邮件向量失败: {e}", exc_info=True)
            return False
    
    def delete_email(self, email_id: int) -> bool:
        """从向量存储删除邮件
        
        Args:
            email_id: 邮件ID
            
        Returns:
            是否成功
        """
        if not self.vector_store:
            return False
        
        try:
            # PGVector删除文档
            # 使用ids参数删除
            self.vector_store.delete(ids=[str(email_id)])
            
            log.info(f"邮件 {email_id} 已从向量存储删除")
            return True
            
        except Exception as e:
            log.error(f"从向量存储删除邮件失败: {e}", exc_info=True)
            # 如果delete方法不存在，尝试其他方式
            try:
                # 尝试使用delete_by_ids方法（某些版本可能使用此方法）
                if hasattr(self.vector_store, 'delete_by_ids'):
                    self.vector_store.delete_by_ids([str(email_id)])
                    return True
            except:
                pass
            return False
    
    def get_retriever(self, k: int = None, filter_dict: Optional[Dict] = None):
        """获取检索器（用于RAG链）
        
        Args:
            k: 返回数量
            filter_dict: 过滤条件
            
        Returns:
            VectorStoreRetriever对象
        """
        if not self.vector_store:
            return None
        
        try:
            search_kwargs = {}
            if filter_dict:
                search_kwargs["filter"] = filter_dict
            if k:
                search_kwargs["k"] = k
            
            retriever = self.vector_store.as_retriever(
                search_kwargs=search_kwargs or {"k": settings.RAG_TOP_K}
            )
            return retriever
            
        except Exception as e:
            log.error(f"创建检索器失败: {e}", exc_info=True)
            return None

