"""邮件相关API路由"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from fastapi.responses import HTMLResponse
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


@router.get("/gmail/callback")
async def gmail_callback(
    code: str = Query(..., description="OAuth授权码"),
    state: Optional[str] = Query(None, description="OAuth state参数"),
    error: Optional[str] = Query(None, description="错误信息"),
    db: Session = Depends(get_db)
):
    """Gmail OAuth回调处理"""
    if error:
        log.error(f"Gmail OAuth授权失败: {error}")
        raise HTTPException(status_code=400, detail=f"授权失败: {error}")
    
    if not code:
        raise HTTPException(status_code=400, detail="缺少授权码")
    
    try:
        # 交换token
        token_data = GmailService.exchange_code_for_token(code)
        
        if not token_data:
            raise HTTPException(status_code=400, detail="获取token失败")
        
        # 创建或更新邮箱账户
        user_email = token_data.get("email")
        if not user_email:
            log.error("token_data中缺少email字段")
            raise HTTPException(status_code=500, detail="无法获取用户邮箱地址")
        
        user = crud.get_user_by_email(db, user_email)
        if not user:
            from backend.db.schemas import UserCreate
            user = crud.create_user(db, UserCreate(email=user_email))
        
        # 检查账户是否已存在
        existing_accounts = crud.get_email_accounts_by_user(db, user.id)
        account = None
        for acc in existing_accounts:
            if acc.email == user_email and acc.provider == models.EmailProvider.GMAIL:
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
                    provider=models.EmailProvider.GMAIL,
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
        
        # 返回HTML成功页面
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Gmail连接成功</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: #f5f5f5;
                }}
                .container {{
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                .success {{
                    color: #4CAF50;
                    font-size: 24px;
                    margin-bottom: 1rem;
                }}
                .message {{
                    color: #666;
                    margin-bottom: 1rem;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✓ 连接成功！</div>
                <div class="message">Gmail账户 ({user_email}) 已成功连接</div>
                <div class="message">窗口将在3秒后自动关闭...</div>
            </div>
            <script>
                // 通知父窗口连接成功
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'gmail_connected', success: true }}, '*');
                }}
                // 3秒后自动关闭
                setTimeout(function() {{
                    window.close();
                }}, 3000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        log.error(f"Gmail OAuth回调处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"连接失败: {str(e)}")


@router.post("/connect")
async def connect_email(
    request: ConnectEmailRequest,
    db: Session = Depends(get_db)
):
    """连接邮箱账户（手动连接，使用授权码）"""
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


@router.post("/fetch")
async def fetch_emails(
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """手动触发获取邮件"""
    account_id = request.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="缺少account_id参数")
    
    account = crud.get_email_account(db, int(account_id))
    if not account:
        raise HTTPException(status_code=404, detail="邮箱账户不存在")
    
    if not account.is_active:
        raise HTTPException(status_code=400, detail="邮箱账户未激活")
    
    try:
        from backend.tasks.email_tasks import fetch_emails_from_account
        result = fetch_emails_from_account.delay(account_id)
        return {"success": True, "task_id": result.id, "message": "邮件获取任务已提交"}
    except Exception as e:
        log.error(f"触发获取邮件任务失败: {e}", exc_info=True)
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


@router.delete("/{email_id}")
async def delete_email(email_id: int, db: Session = Depends(get_db)):
    """删除单封邮件"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")
    
    try:
        # 使用Celery任务异步删除（带延迟以避免限流）
        from backend.tasks.email_tasks import delete_email as delete_email_task
        result = delete_email_task.delay(email_id)
        
        return {
            "success": True,
            "message": "删除任务已提交",
            "task_id": result.id
        }
    except Exception as e:
        log.error(f"提交删除任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-delete")
async def batch_delete_emails(
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """批量删除邮件
    
    Request body:
        {
            "email_ids": [1, 2, 3, ...]
        }
    """
    email_ids = request.get("email_ids", [])
    if not email_ids:
        raise HTTPException(status_code=400, detail="缺少email_ids参数")
    
    if not isinstance(email_ids, list):
        raise HTTPException(status_code=400, detail="email_ids必须是列表")
    
    if len(email_ids) == 0:
        raise HTTPException(status_code=400, detail="email_ids不能为空")
    
    # 验证邮件是否存在
    for email_id in email_ids:
        email = crud.get_email(db, email_id)
        if not email:
            raise HTTPException(status_code=404, detail=f"邮件 {email_id} 不存在")
    
    try:
        # 使用Celery任务批量删除（带延迟以避免限流）
        from backend.tasks.email_tasks import delete_emails_batch
        result = delete_emails_batch.delay(email_ids)
        
        return {
            "success": True,
            "message": f"批量删除任务已提交，共 {len(email_ids)} 封邮件",
            "task_id": result.id,
            "total": len(email_ids)
        }
    except Exception as e:
        log.error(f"提交批量删除任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    tone: str = Query("professional", description="语气: professional, friendly, formal"),
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
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """使用Agent自动处理邮件"""
    email_id = request.get("email_id")
    if not email_id:
        raise HTTPException(status_code=400, detail="缺少email_id参数")
    
    email = crud.get_email(db, int(email_id))
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
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """使用Agent处理复杂查询"""
    query = request.get("query")
    context = request.get("context")
    if not query:
        raise HTTPException(status_code=400, detail="缺少query参数")
    
    try:
        from backend.services.agent_service import AgentService
        agent_service = AgentService()
        full_query = query
        if context:
            context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
            full_query = f"{query}\n\n上下文信息:\n{context_str}"
        result = agent_service.handle_complex_request(full_query)
        
        return result
    except Exception as e:
        log.error(f"Agent查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rag/query")
async def rag_query(
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """基于邮件库的RAG问答"""
    question = request.get("question")
    if not question:
        raise HTTPException(status_code=400, detail="缺少question参数")
    
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

