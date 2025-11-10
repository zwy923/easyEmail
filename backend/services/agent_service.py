"""Agent服务：智能体自动处理邮件"""
from typing import Optional, Dict, List
from langchain.agents import initialize_agent, AgentType
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory

from backend.config import settings
from backend.utils.logging_config import log
from backend.services.agent_tools import get_agent_tools
from backend.services.memory_service import MemoryService
from backend.db.models import Email


class AgentService:
    """Agent服务类"""
    
    def __init__(self):
        self.llm = None
        self.agent = None
        self.memory_service = MemoryService()
        
        if settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0.3,
                api_key=settings.OPENAI_API_KEY
            )
            self._initialize_agent()
    
    def _initialize_agent(self):
        """初始化Agent"""
        if not self.llm:
            return
        
        try:
            # 获取工具列表
            tools = get_agent_tools()
            
            # 创建记忆
            memory = self.memory_service.create_buffer_memory()
            
            # 初始化Agent
            self.agent = initialize_agent(
                tools=tools,
                llm=self.llm,
                agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                verbose=True,
                memory=memory,
                handle_parsing_errors=True
            )
            
            log.info("Agent初始化成功")
            
        except Exception as e:
            log.error(f"初始化Agent失败: {e}", exc_info=True)
    
    def process_email_automatically(self, email: Email) -> Dict:
        """自动处理邮件（分类、生成草稿等）
        
        Args:
            email: 邮件对象
            
        Returns:
            处理结果字典
        """
        if not self.agent:
            log.warning("Agent未初始化，无法自动处理")
            return {"success": False, "message": "Agent未初始化"}
        
        try:
            # 构建任务描述
            task = f"""请处理以下邮件：
邮件ID: {email.id}
发件人: {email.sender_email}
主题: {email.subject}
正文: {(email.body_text or email.body_html or '无正文')[:500]}

请执行以下操作：
1. 先获取邮件详细信息
2. 对邮件进行分类
3. 如果邮件需要回复，生成草稿
4. 根据分类结果决定是否标记为重要或已读

请开始处理："""
            
            # 执行Agent
            # 新版本LangChain可能使用invoke而不是run
            if hasattr(self.agent, 'invoke'):
                result = self.agent.invoke({"input": task})
                if isinstance(result, dict):
                    result = result.get("output", str(result))
            else:
                result = self.agent.run(task)
            
            return {
                "success": True,
                "result": result,
                "email_id": email.id
            }
            
        except Exception as e:
            log.error(f"自动处理邮件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e),
                "email_id": email.id
            }
    
    def handle_complex_request(self, request: str, context: Optional[Dict] = None) -> Dict:
        """处理复杂请求（使用Agent）
        
        Args:
            request: 用户请求
            context: 上下文信息（可选）
            
        Returns:
            处理结果
        """
        if not self.agent:
            return {"success": False, "message": "Agent未初始化"}
        
        try:
            # 构建完整请求
            full_request = request
            if context:
                context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
                full_request = f"{request}\n\n上下文信息:\n{context_str}"
            
            # 执行Agent
            # 新版本LangChain可能使用invoke而不是run
            if hasattr(self.agent, 'invoke'):
                result = self.agent.invoke({"input": full_request})
                if isinstance(result, dict):
                    result = result.get("output", str(result))
            else:
                result = self.agent.run(full_request)
            
            return {
                "success": True,
                "result": result
            }
            
        except Exception as e:
            log.error(f"处理复杂请求失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e)
            }
    
    def batch_process_emails(self, emails: List[Email]) -> List[Dict]:
        """批量处理邮件
        
        Args:
            emails: 邮件列表
            
        Returns:
            处理结果列表
        """
        results = []
        
        for email in emails:
            result = self.process_email_automatically(email)
            results.append(result)
            
            # 避免API调用过快
            import time
            time.sleep(0.5)
        
        log.info(f"批量处理 {len(emails)} 封邮件完成")
        return results
    
    def get_agent_memory(self) -> Optional[ConversationBufferMemory]:
        """获取Agent的记忆对象
        
        Returns:
            记忆对象
        """
        if self.agent and hasattr(self.agent, 'memory'):
            return self.agent.memory
        return None
    
    def clear_agent_memory(self):
        """清空Agent记忆"""
        if self.agent and hasattr(self.agent, 'memory'):
            self.memory_service.clear_memory(self.agent.memory)
            log.info("Agent记忆已清空")

