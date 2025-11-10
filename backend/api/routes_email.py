"""邮件相关API路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.db.database import get_db
from backend.db import crud, models
from backend.db.schemas import (
    EmailResponse, EmailListResponse,
    ClassifyRequest, DraftRequest, ConnectEmailRequest,
    EmailAccountResponse
)
from backend.services.gmail_service import GmailService
from backend.utils.oauth_utils import get_gmail_auth_url, generate_state
from backend.tasks.email_tasks import process_email, generate_draft as generate_draft_task
from backend.utils.logging_config import log

router = APIRouter()


@router.get("/auth-url/{provider}")
async def get_auth_url(provider: str):
    """获取OAuth授权URL"""
    state = generate_state()
    
    if provider.lower() == "gmail":
        auth_url = get_gmail_auth_url(state)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的提供商: {provider}，目前仅支持Gmail")
    
    return {"auth_url": auth_url, "state": state}


@router.post("/connect")
async def connect_email(
    request: ConnectEmailRequest,
    db: Session = Depends(get_db)
):
    """连接邮箱账户（OAuth回调）"""
    try:
        # 交换token
        if request.provider == models.EmailProvider.GMAIL:
            token_data = GmailService.exchange_code_for_token(request.code)
        else:
            raise HTTPException(status_code=400, detail="不支持的提供商，目前仅支持Gmail")
        
        if not token_data:
            raise HTTPException(status_code=400, detail="获取token失败")
        
        # 创建或更新邮箱账户
        # 这里简化处理，实际应该根据用户ID创建
        # 假设用户邮箱就是token_data中的email
        user_email = token_data["email"]
        user = crud.get_user_by_email(db, user_email)
        if not user:
            from backend.db.schemas import UserCreate
            user = crud.create_user(db, UserCreate(email=user_email))
        
        # 检查账户是否已存在
        existing_accounts = crud.get_email_accounts_by_user(db, user.id)
        account = None
        for acc in existing_accounts:
            if acc.email == user_email and acc.provider == request.provider:
                account = acc
                break
        
        if account:
            # 更新token
            crud.update_email_account_token(
                db,
                account.id,
                token_data["access_token"],
                token_data.get("refresh_token"),
                token_data.get("expires_at")
            )
        else:
            # 创建新账户
            from backend.db.schemas import EmailAccountCreate
            account = crud.create_email_account(
                db,
                EmailAccountCreate(
                    provider=request.provider,
                    email=user_email,
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    token_expires_at=token_data.get("expires_at")
                ),
                user.id
            )
        
        # 触发获取邮件任务
        from backend.tasks.email_tasks import fetch_emails_from_account
        fetch_emails_from_account.delay(account.id)
        
        return {"success": True, "account_id": account.id}
        
    except Exception as e:
        log.error(f"连接邮箱失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts", response_model=list[EmailAccountResponse])
async def get_email_accounts(db: Session = Depends(get_db)):
    """获取所有邮箱账户"""
    # 简化处理：返回所有账户
    # 实际应该根据当前用户过滤
    accounts = []
    all_accounts = db.query(models.EmailAccount).all()
    for acc in all_accounts:
        accounts.append(EmailAccountResponse(
            id=acc.id,
            user_id=acc.user_id,
            provider=acc.provider,
            email=acc.email,
            is_active=acc.is_active,
            created_at=acc.created_at,
            updated_at=acc.updated_at
        ))
    return accounts


@router.get("/list", response_model=EmailListResponse)
async def get_emails(
    account_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    sender: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """获取邮件列表"""
    email_status = None
    if status:
        try:
            email_status = models.EmailStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的状态: {status}")
    
    email_category = None
    if category:
        try:
            email_category = models.ClassificationCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的类别: {category}")
    
    emails, total = crud.get_emails(
        db,
        account_id=account_id,
        status=email_status,
        category=email_category,
        sender=sender,
        limit=limit,
        offset=offset
    )
    
    return EmailListResponse(
        total=total,
        items=[EmailResponse.model_validate(email) for email in emails]
    )


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(email_id: int, db: Session = Depends(get_db)):
    """获取邮件详情"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    return EmailResponse.model_validate(email)


@router.post("/classify")
async def classify_email(
    request: ClassifyRequest,
    db: Session = Depends(get_db)
):
    """手动触发邮件分类"""
    email = crud.get_email(db, request.email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    # 异步处理
    result = process_email.delay(request.email_id, force=request.force)
    
    return {"success": True, "task_id": result.id}


@router.post("/draft")
async def create_draft(
    request: DraftRequest,
    db: Session = Depends(get_db)
):
    """生成草稿"""
    email = crud.get_email(db, request.email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    # 异步生成
    result = generate_draft_task.delay(
        request.email_id,
        tone=request.tone,
        length=request.length
    )
    
    return {"success": True, "task_id": result.id}


@router.post("/{email_id}/mark-read")
async def mark_as_read(email_id: int, db: Session = Depends(get_db)):
    """标记邮件为已读"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    # 更新数据库
    crud.update_email(db, email_id, status=models.EmailStatus.READ)
    
    # 更新邮箱中的状态
    account = email.account
    if account.provider == models.EmailProvider.GMAIL:
        service = GmailService(account)
        service.mark_as_read(email.provider_message_id)
    else:
        raise HTTPException(status_code=400, detail="不支持的邮箱提供商")
    
    return {"success": True}


@router.post("/{email_id}/mark-important")
async def mark_as_important(email_id: int, db: Session = Depends(get_db)):
    """标记邮件为重要"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    # 更新数据库
    crud.update_email(db, email_id, is_important=True)
    
    # 更新邮箱中的状态
    account = email.account
    if account.provider == models.EmailProvider.GMAIL:
        service = GmailService(account)
        service.mark_as_important(email.provider_message_id)
    else:
        raise HTTPException(status_code=400, detail="不支持的邮箱提供商")
    
    return {"success": True}


@router.get("/{email_id}/similar")
async def get_similar_emails(
    email_id: int,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """获取相似邮件（基于向量检索）"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    try:
        from backend.services.vector_store import VectorStoreService
        vector_store = VectorStoreService()
        similar_docs = vector_store.get_email_context(email, k=limit)
        
        # 转换为响应格式
        similar_emails = []
        for doc in similar_docs:
            metadata = doc.metadata
            similar_emails.append({
                "email_id": metadata.get("email_id"),
                "subject": metadata.get("subject"),
                "sender": metadata.get("sender"),
                "similarity_content": doc.page_content[:200]
            })
        
        return {"similar_emails": similar_emails}
    except Exception as e:
        log.error(f"获取相似邮件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{email_id}/draft-with-context")
async def generate_draft_with_context(
    email_id: int,
    tone: str = Query("professional"),
    db: Session = Depends(get_db)
):
    """使用RAG上下文生成草稿"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    try:
        from backend.services.rag_service import RAGService
        rag_service = RAGService()
        draft = rag_service.generate_draft_with_context(email, tone=tone)
        
        if not draft:
            raise HTTPException(status_code=500, detail="生成草稿失败")
        
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
        
        return {"success": True, "draft_id": draft_obj.id, "draft": draft}
    except Exception as e:
        log.error(f"生成带上下文的草稿失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/process")
async def agent_process_email(
    email_id: int,
    db: Session = Depends(get_db)
):
    """使用Agent自动处理邮件"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    try:
        from backend.services.agent_service import AgentService
        agent_service = AgentService()
        result = agent_service.process_email_automatically(email)
        
        return result
    except Exception as e:
        log.error(f"Agent处理邮件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/query")
async def agent_query(
    query: str = Query(..., description="查询请求"),
    db: Session = Depends(get_db)
):
    """使用Agent处理复杂查询"""
    try:
        from backend.services.agent_service import AgentService
        agent_service = AgentService()
        result = agent_service.handle_complex_request(query)
        
        return result
    except Exception as e:
        log.error(f"Agent查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/query")
async def rag_query(
    question: str = Query(..., description="问题"),
    db: Session = Depends(get_db)
):
    """基于邮件库的RAG问答"""
    try:
        from backend.services.rag_service import RAGService
        rag_service = RAGService()
        result = rag_service.answer_question(question)
        
        if not result:
            raise HTTPException(status_code=500, detail="RAG查询失败")
        
        return result
    except Exception as e:
        log.error(f"RAG查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

