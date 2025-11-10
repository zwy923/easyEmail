"""Agent工具定义：封装后端函数为可调用工具"""
from typing import List, Optional
from langchain.agents import Tool
from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from backend.utils.logging_config import log
from backend.db import models, crud
from backend.db.database import SessionLocal


class EmailInput(BaseModel):
    """邮件工具输入模型"""
    email_id: int = Field(description="邮件ID")


class EmailToolInput(BaseModel):
    """邮件操作工具输入模型"""
    email_id: int = Field(description="邮件ID")
    action: str = Field(description="操作类型：mark_read, mark_important等")


def get_unread_emails(account_id: Optional[int] = None) -> str:
    """获取未读邮件列表
    
    Args:
        account_id: 邮箱账户ID（可选）
        
    Returns:
        JSON格式的邮件列表字符串
    """
    try:
        db = SessionLocal()
        try:
            emails, total = crud.get_emails(
                db,
                account_id=account_id,
                status=models.EmailStatus.UNREAD,
                limit=20
            )
            
            result = {
                "total": total,
                "emails": [
                    {
                        "id": e.id,
                        "subject": e.subject,
                        "sender": e.sender_email,
                        "received_at": e.received_at.isoformat() if e.received_at else None
                    }
                    for e in emails
                ]
            }
            
            import json
            return json.dumps(result, ensure_ascii=False)
            
        finally:
            db.close()
            
    except Exception as e:
        log.error(f"获取未读邮件失败: {e}", exc_info=True)
        return f"错误: {str(e)}"


def classify_email_tool(email_id: int) -> str:
    """分类邮件工具
    
    Args:
        email_id: 邮件ID
        
    Returns:
        分类结果字符串
    """
    try:
        from backend.services.classification_service import ClassificationService
        
        db = SessionLocal()
        try:
            email = crud.get_email(db, email_id)
            if not email:
                return f"错误: 邮件 {email_id} 不存在"
            
            service = ClassificationService()
            category, confidence = service.classify_email(email)
            
            if category:
                # 更新数据库
                crud.update_email(db, email_id, category=category, classification_confidence=confidence)
                return f"邮件已分类为: {category.value}, 置信度: {confidence}%"
            else:
                return "分类失败"
                
        finally:
            db.close()
            
    except Exception as e:
        log.error(f"分类邮件失败: {e}", exc_info=True)
        return f"错误: {str(e)}"


def generate_draft_tool(email_id: int, tone: str = "professional") -> str:
    """生成草稿工具
    
    Args:
        email_id: 邮件ID
        tone: 语气
        
    Returns:
        生成的草稿内容
    """
    try:
        from backend.services.classification_service import ClassificationService
        
        db = SessionLocal()
        try:
            email = crud.get_email(db, email_id)
            if not email:
                return f"错误: 邮件 {email_id} 不存在"
            
            service = ClassificationService()
            draft = service.generate_draft(email, tone=tone)
            
            if draft:
                # 创建草稿记录
                from backend.db.schemas import DraftCreate
                draft_obj = crud.create_draft(
                    db,
                    DraftCreate(
                        email_id=email_id,
                        subject=f"Re: {email.subject}" if email.subject else "回复",
                        body=draft
                    )
                )
                return f"草稿已生成（ID: {draft_obj.id}）:\n{draft}"
            else:
                return "生成草稿失败"
                
        finally:
            db.close()
            
    except Exception as e:
        log.error(f"生成草稿失败: {e}", exc_info=True)
        return f"错误: {str(e)}"


def mark_email_tool(email_id: int, action: str) -> str:
    """标记邮件工具
    
    Args:
        email_id: 邮件ID
        action: 操作类型（mark_read, mark_important等）
        
    Returns:
        操作结果字符串
    """
    try:
        db = SessionLocal()
        try:
            email = crud.get_email(db, email_id)
            if not email:
                return f"错误: 邮件 {email_id} 不存在"
            
            if action == "mark_read":
                crud.update_email(db, email_id, status=models.EmailStatus.READ)
                return f"邮件 {email_id} 已标记为已读"
            elif action == "mark_important":
                crud.update_email(db, email_id, is_important=True)
                return f"邮件 {email_id} 已标记为重要"
            else:
                return f"错误: 不支持的操作 {action}"
                
        finally:
            db.close()
            
    except Exception as e:
        log.error(f"标记邮件失败: {e}", exc_info=True)
        return f"错误: {str(e)}"


def get_email_details(email_id: int) -> str:
    """获取邮件详情工具
    
    Args:
        email_id: 邮件ID
        
    Returns:
        邮件详情字符串
    """
    try:
        db = SessionLocal()
        try:
            email = crud.get_email(db, email_id)
            if not email:
                return f"错误: 邮件 {email_id} 不存在"
            
            details = f"""邮件详情:
ID: {email.id}
发件人: {email.sender} ({email.sender_email})
主题: {email.subject}
时间: {email.received_at}
状态: {email.status.value}
类别: {email.category.value if email.category else '未分类'}
正文: {(email.body_text or email.body_html or '无正文')[:500]}
"""
            return details
            
        finally:
            db.close()
            
    except Exception as e:
        log.error(f"获取邮件详情失败: {e}", exc_info=True)
        return f"错误: {str(e)}"


# 定义Agent工具列表
def get_agent_tools() -> List[Tool]:
    """获取Agent工具列表
    
    Returns:
        工具列表
    """
    tools = [
        Tool(
            name="get_unread_emails",
            func=lambda account_id: get_unread_emails(account_id) if account_id else get_unread_emails(),
            description="获取未读邮件列表。输入：account_id（可选，整数）"
        ),
        Tool(
            name="get_email_details",
            func=get_email_details,
            description="获取邮件详细信息。输入：email_id（整数）"
        ),
        Tool(
            name="classify_email",
            func=classify_email_tool,
            description="对邮件进行分类（urgent, important, normal, spam, promotion）。输入：email_id（整数）"
        ),
        Tool(
            name="generate_draft",
            func=lambda email_id, tone="professional": generate_draft_tool(email_id, tone),
            description="为邮件生成回复草稿。输入：email_id（整数），tone（可选，professional/friendly/formal）"
        ),
        Tool(
            name="mark_email_read",
            func=lambda email_id: mark_email_tool(email_id, "mark_read"),
            description="将邮件标记为已读。输入：email_id（整数）"
        ),
        Tool(
            name="mark_email_important",
            func=lambda email_id: mark_email_tool(email_id, "mark_important"),
            description="将邮件标记为重要。输入：email_id（整数）"
        ),
    ]
    
    return tools

