"""RAG服务：基于历史邮件的上下文检索和生成"""
from typing import List, Optional, Dict
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

from backend.config import settings
from backend.utils.logging_config import log
from backend.services.vector_store import VectorStoreService
from backend.db.models import Email


class RAGService:
    """RAG服务类"""
    
    def __init__(self):
        self.vector_store_service = VectorStoreService()
        self.llm = None
        self.qa_chain = None
        
        if settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0.7,
                api_key=settings.OPENAI_API_KEY
            )
            self._initialize_qa_chain()
    
    def _initialize_qa_chain(self):
        """初始化QA链"""
        if not self.llm or not self.vector_store_service.vector_store:
            return
        
        try:
            # 获取检索器
            retriever = self.vector_store_service.get_retriever()
            if not retriever:
                return
            
            # 创建自定义提示词
            prompt_template = """使用以下上下文信息回答用户的问题。如果你不知道答案，就说你不知道，不要编造答案。

上下文信息：
{context}

问题：{question}

回答："""
            
            PROMPT = PromptTemplate(
                template=prompt_template,
                input_variables=["context", "question"]
            )
            
            # 创建RetrievalQA链
            # 注意：新版本LangChain可能使用不同的API
            try:
                # 尝试使用旧版API
                self.qa_chain = RetrievalQA.from_chain_type(
                    llm=self.llm,
                    chain_type="stuff",
                    retriever=retriever,
                    return_source_documents=True,
                    chain_type_kwargs={"prompt": PROMPT}
                )
            except (AttributeError, TypeError) as e:
                # 如果from_chain_type不存在或API改变，尝试使用新的API
                log.warning(f"使用旧API失败，尝试新API: {e}")
                try:
                    from langchain.chains import create_retrieval_chain
                    from langchain.chains.combine_documents import create_stuff_documents_chain
                    
                    document_chain = create_stuff_documents_chain(self.llm, PROMPT)
                    self.qa_chain = create_retrieval_chain(retriever, document_chain)
                except (ImportError, AttributeError) as e2:
                    # 如果新API也不可用，使用简化版本
                    log.warning(f"RetrievalQA API不可用，使用简化实现: {e2}")
                    self.qa_chain = None
            except Exception as e:
                log.error(f"创建RetrievalQA链失败: {e}", exc_info=True)
                self.qa_chain = None
            
            log.info("RAG QA链初始化成功")
            
        except Exception as e:
            log.error(f"初始化RAG QA链失败: {e}", exc_info=True)
    
    def get_email_context(self, email: Email, k: int = None) -> List[Document]:
        """获取邮件的上下文（相似历史邮件）
        
        Args:
            email: 邮件对象
            k: 返回数量
            
        Returns:
            相似邮件Document列表
        """
        return self.vector_store_service.get_email_context(email, k=k)
    
    def generate_draft_with_context(
        self,
        email: Email,
        context_emails: Optional[List[Email]] = None,
        tone: str = "professional"
    ) -> Optional[str]:
        """基于上下文生成草稿
        
        Args:
            email: 原始邮件
            context_emails: 上下文邮件列表（如果为None，则自动检索）
            tone: 语气
            
        Returns:
            生成的草稿
        """
        if not self.llm:
            log.warning("LLM未初始化，无法生成草稿")
            return None
        
        try:
            # 获取上下文
            if context_emails is None:
                context_docs = self.get_email_context(email)
            else:
                # 从提供的邮件创建Document
                context_docs = [
                    self.vector_store_service.embedding_service.create_document(e)
                    for e in context_emails
                    if self.vector_store_service.embedding_service.create_document(e)
                ]
            
            # 构建上下文文本
            context_text = ""
            if context_docs:
                context_parts = []
                for doc in context_docs[:5]:  # 限制上下文数量
                    metadata = doc.metadata
                    context_parts.append(
                        f"相关邮件（{metadata.get('subject', '无主题')}，"
                        f"发件人: {metadata.get('sender', '未知')}）:\n"
                        f"{doc.page_content[:500]}\n"
                    )
                context_text = "\n".join(context_parts)
            
            # 构建提示词
            # 先构建上下文部分（避免在f-string表达式中使用反斜杠）
            context_section = ""
            if context_text:
                context_section = f"历史上下文：\n{context_text}\n"
            
            prompt = f"""请根据以下邮件和上下文信息生成回复：

原邮件：
发件人: {email.sender} ({email.sender_email})
主题: {email.subject}
正文: {email.body_text or email.body_html or '无正文'}

{context_section}
要求：
- 语气: {tone}
- 回复应该针对原邮件的内容
- 如果上下文中有相关信息，可以适当参考
- 不要包含"回复"、"Re:"等前缀
- 直接写回复内容

请生成回复："""
            
            # 使用LLM生成
            from langchain_core.messages import HumanMessage
            response = self.llm.invoke([HumanMessage(content=prompt)])
            draft = response.content.strip()
            
            log.info(f"为邮件 {email.id} 生成带上下文的草稿成功")
            return draft
            
        except Exception as e:
            log.error(f"生成带上下文的草稿失败: {e}", exc_info=True)
            return None
    
    def answer_question(
        self,
        question: str,
        filter_dict: Optional[Dict] = None
    ) -> Optional[Dict]:
        """基于邮件库回答问题（使用RAG链）
        
        Args:
            question: 问题
            filter_dict: 过滤条件
            
        Returns:
            包含答案和来源的字典
        """
        if not self.qa_chain:
            log.warning("RAG QA链未初始化")
            return None
        
        try:
            # 执行查询
            # 根据不同的API版本处理
            if hasattr(self.qa_chain, 'invoke'):
                # 新版本API
                result = self.qa_chain.invoke({"input": question})
                answer = result.get("answer", result.get("output", ""))
                source_docs = result.get("context", [])
            else:
                # 旧版本API
                result = self.qa_chain({"query": question})
                answer = result.get("result", "")
                source_docs = result.get("source_documents", [])
            
            # 处理source_documents
            source_documents = []
            for doc in source_docs:
                if hasattr(doc, 'page_content'):
                    source_documents.append({
                        "content": doc.page_content,
                        "metadata": doc.metadata if hasattr(doc, 'metadata') else {}
                    })
                elif isinstance(doc, dict):
                    source_documents.append(doc)
            
            return {
                "answer": answer,
                "source_documents": source_documents
            }
            
        except Exception as e:
            log.error(f"RAG问答失败: {e}", exc_info=True)
            return None
    
    def search_related_emails(
        self,
        query: str,
        k: int = None,
        filter_dict: Optional[Dict] = None
    ) -> List[Document]:
        """搜索相关邮件
        
        Args:
            query: 查询文本
            k: 返回数量
            filter_dict: 过滤条件
            
        Returns:
            相关邮件Document列表
        """
        return self.vector_store_service.search_similar_emails(
            query,
            k=k,
            filter_dict=filter_dict
        )

