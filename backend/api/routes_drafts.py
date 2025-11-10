"""草稿相关API路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.db.database import get_db
from backend.db import crud, models
from backend.db.schemas import DraftResponse, DraftCreate
from backend.services.gmail_service import GmailService
from backend.utils.logging_config import log

router = APIRouter()


@router.get("", response_model=List[DraftResponse])
async def get_drafts(
    email_id: Optional[int] = Query(None, description="邮件ID过滤"),
    limit: int = Query(50, ge=1, le=100, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db)
):
    """获取草稿列表"""
    if email_id:
        drafts = crud.get_drafts_by_email(db, email_id)
    else:
        # 获取所有草稿
        drafts = db.query(models.Draft).order_by(models.Draft.created_at.desc()).offset(offset).limit(limit).all()
    
    # 转换为响应格式，添加to字段（从关联的email获取）
    result = []
    for draft in drafts:
        draft_data = DraftResponse.model_validate(draft).model_dump()
        # 获取关联的邮件以获取收件人
        email = crud.get_email(db, draft.email_id)
        if email:
            draft_data['to'] = email.sender_email
        result.append(draft_data)
    
    return result


@router.get("/{draft_id}")
async def get_draft(draft_id: int, db: Session = Depends(get_db)):
    """获取草稿详情"""
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    
    draft_data = DraftResponse.model_validate(draft).model_dump()
    # 获取关联的邮件以获取收件人
    email = crud.get_email(db, draft.email_id)
    if email:
        draft_data['to'] = email.sender_email
    
    return draft_data


@router.post("/{draft_id}/send")
async def send_draft(
    draft_id: int,
    db: Session = Depends(get_db)
):
    """发送草稿"""
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    
    if draft.is_sent:
        raise HTTPException(status_code=400, detail="草稿已发送")
    
    try:
        email = crud.get_email(db, draft.email_id)
        if not email:
            raise HTTPException(status_code=404, detail="关联邮件不存在")
        
        account = email.account
        if account.provider == models.EmailProvider.GMAIL:
            service = GmailService(account)
            # 发送邮件
            service.send_message(
                to=email.sender_email,
                subject=draft.subject or f"Re: {email.subject}",
                body=draft.body,
                thread_id=email.thread_id
            )
            
            # 更新草稿状态
            crud.update_draft(db, draft_id, is_sent=True)
            
            return {"success": True, "message": "草稿已发送"}
        else:
            raise HTTPException(status_code=400, detail="不支持的邮箱提供商")
    except Exception as e:
        log.error(f"发送草稿失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{draft_id}")
async def delete_draft(
    draft_id: int,
    db: Session = Depends(get_db)
):
    """删除草稿"""
    draft = db.query(models.Draft).filter(models.Draft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="草稿不存在")
    
    try:
        # 如果草稿在邮箱提供商中存在，先删除
        if draft.provider_draft_id:
            email = crud.get_email(db, draft.email_id)
            if email and email.account:
                account = email.account
                if account.provider == models.EmailProvider.GMAIL:
                    service = GmailService(account)
                    try:
                        service.delete_draft(draft.provider_draft_id)
                    except Exception as e:
                        log.warning(f"删除邮箱中的草稿失败: {e}")
        
        # 删除数据库中的草稿
        db.delete(draft)
        db.commit()
        
        return {"success": True, "message": "草稿已删除"}
    except Exception as e:
        db.rollback()
        log.error(f"删除草稿失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

