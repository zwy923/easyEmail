"""Email listing and management routes."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db import crud, models
from backend.db.database import get_db
from backend.db.schemas import (
    ClassifyRequest,
    DraftRequest,
    EmailListResponse,
    EmailResponse,
)
from backend.services.gmail_service import GmailService
from backend.tasks.email_tasks import (
    delete_email as delete_email_task,
    delete_emails_batch,
    generate_draft as generate_draft_task,
    process_email,
    sync_email_status as sync_status_task,
)
from backend.utils.logging_config import log

router = APIRouter()


def _trigger_deleted_cleanup(email_ids: List[int]) -> None:
    """Trigger background cleanup for deleted emails."""
    for email_id in email_ids:
        try:
            delete_email_task.apply_async(args=[email_id], countdown=1)
            log.info(f"已提交删除任务以清理邮件 {email_id}（Gmail中不存在）")
        except Exception as exc:
            log.warning(f"为邮件 {email_id} 提交删除任务失败: {exc}")


@router.get("/list", response_model=EmailListResponse)
async def get_emails(
    account_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    sender: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sync_deleted: bool = Query(False, description="是否同步检查已删除的邮件"),
    db: Session = Depends(get_db)
):
    """获取邮件列表"""
    task_ids: List[str] = []
    if sync_deleted:
        try:
            accounts = crud.get_active_email_accounts(db)
            if account_id:
                accounts = [acc for acc in accounts if acc.id == account_id]

            for account in accounts:
                if account.provider == models.EmailProvider.GMAIL:
                    result = sync_status_task.delay(account.id)
                    task_ids.append(result.id)
                    log.info(f"触发账户 {account.id} 的删除状态同步任务: {result.id}")

            if task_ids:
                log.info(f"已触发 {len(task_ids)} 个同步任务，继续返回当前邮件列表")
        except Exception as exc:
            log.warning(f"触发删除状态同步任务失败: {exc}")

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

    removed_ids: List[int] = []
    if sync_deleted and emails:
        services: Dict[int, GmailService] = {}
        for email in emails:
            account = email.account
            if not account or account.provider != models.EmailProvider.GMAIL:
                continue

            if account.id not in services:
                services[account.id] = GmailService(account)
            service = services[account.id]

            try:
                exists = service.check_message_exists(email.provider_message_id)
            except Exception as exc:
                log.warning(f"检查Gmail邮件 {email.id} 是否存在失败: {exc}")
                continue

            if not exists:
                log.info(f"邮件 {email.id} 在Gmail中已删除，立即在数据库中标记")
                crud.update_email(db, email.id, status=models.EmailStatus.DELETED)
                removed_ids.append(email.id)

        if removed_ids:
            _trigger_deleted_cleanup(removed_ids)
            emails, total = crud.get_emails(
                db,
                account_id=account_id,
                status=email_status,
                category=email_category,
                sender=sender,
                limit=limit,
                offset=offset
            )

    response_dict = {
        "total": total,
        "items": [EmailResponse.model_validate(email) for email in emails]
    }

    if sync_deleted:
        if task_ids:
            response_dict["task_id"] = task_ids[0]
            response_dict["task_ids"] = task_ids
        if removed_ids:
            response_dict["deleted_ids"] = removed_ids

    if sync_deleted and (task_ids or removed_ids):
        return response_dict

    return EmailListResponse(**response_dict)


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(email_id: int, db: Session = Depends(get_db)):
    """获取邮件详情"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    if email.status == models.EmailStatus.DELETED:
        raise HTTPException(status_code=404, detail="邮件已被删除")

    return EmailResponse.model_validate(email)


@router.post("/classify")
async def classify_email(
    request: Optional[ClassifyRequest] = Body(None),
    db: Session = Depends(get_db)
):
    """手动触发邮件分类"""
    if request and request.email_id:
        email = crud.get_email(db, request.email_id)
        if not email:
            raise HTTPException(status_code=404, detail="邮件不存在")

        result = process_email.delay(request.email_id, force_classify=request.force if request.force else False)
        return {"success": True, "task_id": result.id, "message": "分类任务已提交"}
    else:
        from sqlalchemy import desc
        from backend.db.models import Email

        unclassified_emails = db.query(Email).filter(
            Email.category == None
        ).order_by(desc(Email.received_at)).limit(10).all()

        if not unclassified_emails:
            return {
                "success": True,
                "message": "没有未分类的邮件",
                "classified_count": 0
            }

        task_ids: List[str] = []
        for email in unclassified_emails:
            result = process_email.delay(email.id, force_classify=False)
            task_ids.append(result.id)

        log.info(f"已提交 {len(unclassified_emails)} 封邮件的分类任务")
        return {
            "success": True,
            "task_ids": task_ids,
            "task_id": task_ids[0] if task_ids else None,
            "classified_count": len(unclassified_emails),
            "message": f"已提交 {len(unclassified_emails)} 封邮件的分类任务"
        }


@router.post("/draft")
async def create_draft(
    request: DraftRequest,
    db: Session = Depends(get_db)
):
    """生成草稿"""
    email = crud.get_email(db, request.email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

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

    crud.update_email(db, email_id, status=models.EmailStatus.READ)

    account = email.account
    if account.provider == models.EmailProvider.GMAIL:
        service = GmailService(account)
        service.mark_as_read(email.provider_message_id)
    else:
        raise HTTPException(status_code=400, detail="不支持的邮箱提供商")

    return {"success": True}


@router.post("/{email_id}/mark-unread")
async def mark_as_unread(email_id: int, db: Session = Depends(get_db)):
    """标记邮件为未读"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    crud.update_email(db, email_id, status=models.EmailStatus.UNREAD)

    account = email.account
    if account.provider == models.EmailProvider.GMAIL:
        service = GmailService(account)
        service.mark_as_unread(email.provider_message_id)
    else:
        raise HTTPException(status_code=400, detail="不支持的邮箱提供商")

    return {"success": True}


@router.post("/{email_id}/mark-important")
async def mark_as_important(email_id: int, db: Session = Depends(get_db)):
    """标记邮件为重要"""
    email = crud.get_email(db, email_id)
    if not email:
        raise HTTPException(status_code=404, detail="邮件不存在")

    crud.update_email(db, email_id, is_important=True)

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
        crud.update_email(db, email_id, status=models.EmailStatus.DELETED)

        result = delete_email_task.delay(email_id)

        return {
            "success": True,
            "message": "删除任务已提交，邮件已标记为已删除",
            "task_id": result.id
        }
    except Exception as exc:
        log.error(f"提交删除任务失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/batch-delete")
async def batch_delete_emails(
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """批量删除邮件"""
    email_ids = request.get("email_ids", [])
    if not email_ids:
        raise HTTPException(status_code=400, detail="缺少email_ids参数")

    if not isinstance(email_ids, list):
        raise HTTPException(status_code=400, detail="email_ids必须是列表")

    if len(email_ids) == 0:
        raise HTTPException(status_code=400, detail="email_ids不能为空")

    for email_id in email_ids:
        email = crud.get_email(db, email_id)
        if not email:
            raise HTTPException(status_code=404, detail=f"邮件 {email_id} 不存在")

    try:
        for eid in email_ids:
            try:
                crud.update_email(db, eid, status=models.EmailStatus.DELETED)
            except Exception:
                log.warning(f"将邮件 {eid} 标记为已删除时失败")

        result = delete_emails_batch.delay(email_ids)

        return {
            "success": True,
            "message": f"批量删除任务已提交，共 {len(email_ids)} 封邮件，已在数据库中标记为已删除",
            "task_id": result.id,
            "total": len(email_ids)
        }
    except Exception as exc:
        log.error(f"提交批量删除任务失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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
    except Exception as exc:
        log.error(f"获取相似邮件失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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
    except Exception as exc:
        log.error(f"生成带上下文的草稿失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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
    except Exception as exc:
        log.error(f"Agent处理邮件失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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
    except Exception as exc:
        log.error(f"Agent查询失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


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
    except Exception as exc:
        log.error(f"RAG查询失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
