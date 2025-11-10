"""LangChain相关Pydantic模型"""
from pydantic import BaseModel, Field
from typing import Optional
from backend.db.models import ClassificationCategory


class ClassificationResult(BaseModel):
    """分类结果模型"""
    category: ClassificationCategory = Field(description="邮件分类类别")
    confidence: int = Field(description="置信度(0-100)", ge=0, le=100)
    reasoning: Optional[str] = Field(default=None, description="分类理由")


class DraftGenerationResult(BaseModel):
    """草稿生成结果模型"""
    draft: str = Field(description="生成的草稿内容")
    tone: str = Field(description="使用的语气")
    length: str = Field(description="草稿长度")

