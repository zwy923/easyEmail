"""Routes related to email synchronisation and background tasks."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db import crud
from backend.db.database import get_db
from backend.tasks.email_tasks import fetch_emails_from_account, sync_email_status as sync_status_task
from backend.utils.logging_config import log

router = APIRouter()


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
        result = fetch_emails_from_account.delay(account_id)
        return {"success": True, "task_id": result.id, "message": "邮件获取任务已提交"}
    except Exception as exc:
        log.error(f"触发获取邮件任务失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync-status")
async def sync_email_status(
    request: dict = Body(...),
    db: Session = Depends(get_db)
):
    """同步邮件的已读/未读状态（从Gmail同步到数据库）"""
    account_id = request.get("account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="缺少account_id参数")

    account = crud.get_email_account(db, int(account_id))
    if not account:
        raise HTTPException(status_code=404, detail="邮箱账户不存在")

    if not account.is_active:
        raise HTTPException(status_code=400, detail="邮箱账户未激活")

    try:
        result = sync_status_task.delay(account_id)
        return {
            "success": True,
            "task_id": result.id,
            "message": "状态同步任务已提交"
        }
    except Exception as exc:
        log.error(f"触发状态同步任务失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态和进度"""
    try:
        from celery.result import AsyncResult
        from backend.celery_worker import celery_app

        task_result = AsyncResult(task_id, app=celery_app)

        if task_result.state == 'PENDING':
            response = {
                'state': task_result.state,
                'current': 0,
                'total': 0,
                'percent': 0,
                'status': '等待中...'
            }
        elif task_result.state == 'PROGRESS':
            meta = task_result.info or {}
            response = {
                'state': task_result.state,
                'current': meta.get('current', 0),
                'total': meta.get('total', 0),
                'percent': meta.get('percent', 0),
                'status': meta.get('status', '处理中...'),
                **{k: v for k, v in meta.items() if k not in ['current', 'total', 'percent', 'status']}
            }
        elif task_result.state == 'SUCCESS':
            result = task_result.result if isinstance(task_result.result, dict) else {}
            meta = task_result.info if isinstance(task_result.info, dict) else {}
            response = {
                'state': task_result.state,
                'current': meta.get('current', result.get('total', 0)),
                'total': meta.get('total', result.get('total', 0)),
                'percent': 100,
                'status': '完成',
                **result,
                **{k: v for k, v in meta.items() if k not in ['current', 'total', 'percent', 'status']}
            }
        else:
            response = {
                'state': task_result.state,
                'current': 0,
                'total': 0,
                'percent': 0,
                'status': f'状态: {task_result.state}',
                'error': str(task_result.info) if task_result.info else None
            }

        return response
    except Exception as exc:
        log.error(f"获取任务状态失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """取消任务（只能取消PENDING状态的任务）"""
    try:
        from celery.result import AsyncResult
        from backend.celery_worker import celery_app

        task_result = AsyncResult(task_id, app=celery_app)

        if task_result.state == 'PENDING':
            celery_app.control.revoke(task_id, terminate=True)
            log.info(f"任务 {task_id} 已取消")
            return {"success": True, "message": "任务已取消"}
        elif task_result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            return {"success": False, "message": f"任务已完成或已取消，当前状态: {task_result.state}"}
        else:
            celery_app.control.revoke(task_id, terminate=True)
            log.warning(f"尝试终止正在执行的任务 {task_id}，状态: {task_result.state}")
            return {"success": True, "message": f"已尝试终止任务（状态: {task_result.state}）"}
    except Exception as exc:
        log.error(f"取消任务失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/tasks/purge")
async def purge_tasks(
    request: dict = Body(...)
):
    """清空所有待处理的任务队列"""
    try:
        from backend.celery_worker import celery_app

        task_name = request.get("task_name")

        if task_name:
            celery_app.control.purge()
            log.warning(f"已清空任务队列（任务类型: {task_name}）")
            return {
                "success": True,
                "message": f"已清空任务队列（任务类型: {task_name}）"
            }
        else:
            celery_app.control.purge()
            log.warning("已清空所有任务队列")
            return {
                "success": True,
                "message": "已清空所有任务队列"
            }
    except Exception as exc:
        log.error(f"清空任务队列失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
