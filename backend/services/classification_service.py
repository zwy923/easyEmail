"""邮件分类和草稿生成服务（使用LangChain）"""
from typing import Optional, Dict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import settings
from backend.utils.logging_config import log
from backend.db.models import Email, ClassificationCategory
from backend.services.schemas import ClassificationResult, DraftGenerationResult


class ClassificationService:
    """分类服务类（使用LangChain）"""
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            log.warning("OpenAI API密钥未配置")
            self.llm = None
        else:
            self.llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0.3,
                api_key=settings.OPENAI_API_KEY
            )
        
        # 分类结果解析器
        self.classification_parser = PydanticOutputParser(pydantic_object=ClassificationResult)
        
        # 分类提示词模板
        self.classification_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                "你是一个专业的邮件分类助手。根据邮件内容，将其分类为以下类别之一："
                "urgent（紧急）、important（重要）、normal（普通）、spam（垃圾邮件）、promotion（促销）。"
                "\n\n{format_instructions}"
            ),
            HumanMessagePromptTemplate.from_template(
                "请分析以下邮件并分类：\n\n"
                "发件人: {sender} ({sender_email})\n"
                "主题: {subject}\n"
                "正文:\n{body_text}\n\n"
                "请返回分类结果："
            )
        ])
        
        # 草稿生成提示词模板
        self.draft_prompt_template = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                "你是一个专业的邮件回复助手。根据收到的邮件，生成合适的回复。"
                "回复应该礼貌、专业且切题。"
            ),
            HumanMessagePromptTemplate.from_template(
                "请为以下邮件生成回复：\n\n"
                "原邮件：\n"
                "发件人: {sender} ({sender_email})\n"
                "主题: {subject}\n"
                "正文:\n{body_text}\n\n"
                "要求：\n"
                "- 语气: {tone_description}\n"
                "- 长度: {length_description}\n"
                "- 回复应该针对原邮件的内容\n"
                "- 不要包含\"回复\"、\"Re:\"等前缀\n"
                "- 直接写回复内容\n\n"
                "请生成回复："
            )
        ])
    
    def classify_email(self, email: Email) -> tuple[Optional[ClassificationCategory], Optional[int]]:
        """分类邮件
        
        Returns:
            (category, confidence): 分类类别和置信度(0-100)
        """
        if not self.llm:
            log.warning("OpenAI API密钥未配置，无法进行分类")
            return None, None
        
        try:
            # 构建提示词
            format_instructions = self.classification_parser.get_format_instructions()
            
            messages = self.classification_prompt.format_messages(
                format_instructions=format_instructions,
                sender=email.sender or "",
                sender_email=email.sender_email or "",
                subject=email.subject or "(无主题)",
                body_text=(email.body_text or email.body_html or "无正文")[:1000]
            )
            
            # 执行分类
            response = self.llm.invoke(messages)
            
            # 解析结果
            try:
                result = self.classification_parser.parse(response.content)
                category = result.category
                confidence = result.confidence
                
                log.info(f"邮件 {email.id} 分类结果: {category.value}, 置信度: {confidence}")
                if result.reasoning:
                    log.debug(f"分类理由: {result.reasoning}")
                
                return category, confidence
            except Exception as parse_error:
                log.warning(f"解析分类结果失败，使用默认分类: {parse_error}")
                # 回退到简单解析
                content = response.content.lower()
                category = ClassificationCategory.NORMAL
                confidence = 80
                
                for cat in ClassificationCategory:
                    if cat.value in content:
                        category = cat
                        break
                
                return category, confidence
            
        except Exception as e:
            log.error(f"分类邮件失败: {e}", exc_info=True)
            return None, None
    
    def generate_draft(
        self,
        email: Email,
        tone: str = "professional",
        length: str = "medium"
    ) -> Optional[str]:
        """生成草稿回复
        
        Args:
            email: 原始邮件
            tone: 语气 (professional, friendly, formal)
            length: 长度 (short, medium, long)
        """
        if not self.llm:
            log.warning("OpenAI API密钥未配置，无法生成草稿")
            return None
        
        try:
            tone_descriptions = {
                "professional": "专业、礼貌、正式",
                "friendly": "友好、亲切、轻松",
                "formal": "正式、严谨、官方"
            }
            
            length_descriptions = {
                "short": "简短（2-3句话）",
                "medium": "中等长度（一段话）",
                "long": "详细（多段话）"
            }
            
            # 构建提示词
            messages = self.draft_prompt_template.format_messages(
                sender=email.sender or "",
                sender_email=email.sender_email or "",
                subject=email.subject or "(无主题)",
                body_text=email.body_text or email.body_html or "无正文",
                tone_description=tone_descriptions.get(tone, "professional"),
                length_description=length_descriptions.get(length, "medium")
            )
            
            # 根据长度创建不同配置的LLM实例
            max_tokens = 500 if length == "short" else (800 if length == "medium" else 1200)
            
            # 创建用于生成草稿的LLM实例（使用更高的temperature和max_tokens）
            draft_llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0.7,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=max_tokens
            )
            
            # 执行生成
            response = draft_llm.invoke(messages)
            
            draft = response.content.strip()
            log.info(f"为邮件 {email.id} 生成草稿成功")
            return draft
            
        except Exception as e:
            log.error(f"生成草稿失败: {e}", exc_info=True)
            return None
    
    def generate_draft_with_context(
        self,
        email: Email,
        context: str,
        tone: str = "professional"
    ) -> Optional[str]:
        """根据上下文生成草稿"""
        if not self.llm:
            return None
        
        try:
            # 构建带上下文的提示词
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content="你是一个专业的邮件回复助手。"),
                HumanMessage(content=f"""请根据以下信息生成邮件回复：

原邮件：
发件人: {email.sender} ({email.sender_email})
主题: {email.subject}
正文: {(email.body_text or email.body_html or '无正文')[:1000]}

额外上下文：
{context}

请生成一个{tone}语气的回复：""")
            ])
            
            # 创建临时LLM实例用于生成草稿（使用更高的temperature）
            draft_llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0.7,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=800
            )
            response = draft_llm.invoke(prompt.format_messages())
            return response.content.strip()
            
        except Exception as e:
            log.error(f"生成上下文草稿失败: {e}", exc_info=True)
            return None
