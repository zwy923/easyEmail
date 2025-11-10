"""Celery异步任务定义"""
from celery import Task
from typing import List
from datetime import datetime

from backend.celery_worker import celery_app
from backend.utils.logging_config import log
from backend.db.database import SessionLocal
from backend.db import crud, models
from backend.services.gmail_service import GmailService
from backend.services.classification_service import ClassificationService


class DatabaseTask(Task):
    """带数据库会话的任务基类"""
    _db = None
    
    @property
    def db(self):
        if self._db is None:
            self._db = SessionLocal()
        return self._db
    
    def after_return(self, *args, **kwargs):
        """任务完成后关闭数据库会话"""
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=DatabaseTask, bind=True)
def fetch_emails_from_account(self, account_id: int):
    """从邮箱账户获取新邮件"""
    db = self.db
    try:
        account = crud.get_email_account(db, account_id)
        if not account or not account.is_active:
            log.warning(f"邮箱账户 {account_id} 不存在或未激活")
            return {"success": False, "message": "账户不存在或未激活"}
        
        # 根据提供商选择服务
        if account.provider == models.EmailProvider.GMAIL:
            service = GmailService(account)
        else:
            return {"success": False, "message": f"不支持的提供商: {account.provider}，目前仅支持Gmail"}
        
        # 获取邮件列表（获取所有邮件）
        messages = service.get_messages(fetch_all=True)
        new_count = 0
        skipped_count = 0
        error_count = 0
        total_messages = len(messages)
        log.info(f"账户 {account_id} 从Gmail获取到 {total_messages} 封邮件，开始处理...")
        
        # 更新任务状态：开始处理
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': total_messages,
                'percent': 0,
                'new_count': 0,
                'skipped_count': 0,
                'error_count': 0,
                'status': '开始处理...'
            }
        )
        
        try:
            from backend.services.vector_store import VectorStoreService
            vector_store = VectorStoreService()
        except Exception as e:
            vector_store = None
            log.warning(f"初始化向量存储服务失败: {e}", exc_info=True)

        for idx, msg in enumerate(messages, 1):
            # 每处理10封邮件更新一次进度（更频繁的更新）
            if idx % 10 == 0 or idx == total_messages:
                percent = idx * 100 // total_messages
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': total_messages,
                        'percent': percent,
                        'new_count': new_count,
                        'skipped_count': skipped_count,
                        'error_count': error_count,
                        'status': f'处理中: {idx}/{total_messages} ({percent}%)'
                    }
                )
                log.info(f"处理进度: {idx}/{total_messages} ({percent}%), 新增: {new_count}, 跳过: {skipped_count}, 错误: {error_count}")
            
            message_id = msg.get("id")
            
            # 检查邮件是否已存在
            existing = crud.get_email_by_provider_id(db, message_id)
            if existing:
                # 同步已存在邮件的状态（从Gmail获取最新状态）
                # 注意：使用get_message_status只获取metadata，不获取完整邮件内容，以提高性能
                try:
                    # 首先检查邮件是否还存在并获取最新状态
                    exists, gmail_status = service.get_message_state(message_id)
                    if not exists:
                        # 邮件在Gmail中已删除，标记为已删除
                        from backend.db.models import EmailStatus
                        if existing.status != EmailStatus.DELETED:
                            crud.update_email(db, existing.id, status=EmailStatus.DELETED)
                            log.info(f"邮件 {existing.id} (message_id: {message_id}) 在Gmail中已删除，已标记为DELETED")
                        skipped_count += 1
                        continue

                    # 邮件存在，同步状态
                    if gmail_status:
                        # 将Gmail状态转换为数据库状态
                        from backend.db.models import EmailStatus
                        if gmail_status == 'unread':
                            db_status = EmailStatus.UNREAD
                        else:
                            db_status = EmailStatus.READ
                        
                        # 如果状态不一致，更新数据库
                        if existing.status != db_status:
                            crud.update_email(db, existing.id, status=db_status)
                            log.debug(f"同步邮件 {existing.id} (message_id: {message_id}) 状态: {existing.status.value} -> {db_status.value}")
                except Exception as e:
                    log.warning(f"同步邮件 {existing.id} (message_id: {message_id}) 状态失败: {e}")
                
                skipped_count += 1
                # 只在每50封邮件时记录一次跳过信息，避免日志过多
                if skipped_count % 50 == 0:
                    log.debug(f"已跳过 {skipped_count} 封已存在的邮件")
                continue
            
            # 获取邮件详情
            try:
                email_data = service.get_message(message_id)
                if not email_data:
                    error_count += 1
                    log.warning(f"无法获取邮件详情: {message_id}")
                    continue
            except Exception as e:
                error_count += 1
                log.warning(f"获取邮件详情失败 {message_id}: {e}")
                continue
            
            # 创建邮件记录
            from backend.db.schemas import EmailCreate
            from backend.db.models import EmailStatus
            
            # 根据Gmail返回的状态设置数据库状态
            gmail_status = email_data.get("status", "unread")
            if gmail_status == "unread":
                db_status = EmailStatus.UNREAD
            else:
                db_status = EmailStatus.READ
            
            email_create = EmailCreate(
                account_id=account_id,
                provider_message_id=message_id,
                thread_id=email_data.get("thread_id"),
                subject=email_data.get("subject"),
                sender=email_data.get("sender"),
                sender_email=email_data.get("sender_email"),
                recipients=email_data.get("recipients", []),
                cc=email_data.get("cc", []),
                bcc=email_data.get("bcc", []),
                body_text=email_data.get("body_text"),
                body_html=email_data.get("body_html"),
                received_at=email_data.get("received_at") or datetime.utcnow(),
                labels=email_data.get("labels", []),
                status=db_status  # 使用从Gmail同步的状态
            )
            
            email = crud.create_email(db, email_create)
            new_count += 1
            
            # 添加到向量存储
            if vector_store:
                try:
                    success = vector_store.add_email(email)
                    if not success:
                        log.warning(f"添加邮件 {email.id} 到向量存储失败（返回False）")
                except Exception as e:
                    log.warning(f"添加邮件 {email.id} 到向量存储失败: {e}", exc_info=True)
            
            # 不再自动分类，只有用户手动点击分类按钮时才会分类
        
        log.info(f"账户 {account_id} 处理完成: 总计 {total_messages} 封，新增 {new_count} 封，跳过 {skipped_count} 封，错误 {error_count} 封")
        if new_count == 0 and skipped_count > 0:
            log.info(f"提示: 所有邮件都已存在于数据库中，没有新邮件。如需重新处理，请考虑清理数据库或等待新邮件。")
        
        # 更新任务状态：完成
        self.update_state(
            state='SUCCESS',
            meta={
                'current': total_messages,
                'total': total_messages,
                'percent': 100,
                'new_count': new_count,
                'skipped_count': skipped_count,
                'error_count': error_count,
                'status': '处理完成'
            }
        )
        
        return {
            "success": True, 
            "total_messages": total_messages,
            "new_count": new_count,
            "skipped_count": skipped_count,
            "error_count": error_count
        }
        
    except Exception as e:
        log.error(f"获取邮件失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def process_email(self, email_id: int, force_classify: bool = False):
    """处理邮件：分类"""
    db = self.db
    try:
        email = crud.get_email(db, email_id)
        if not email:
            log.warning(f"邮件 {email_id} 不存在")
            return {"success": False, "message": "邮件不存在"}
        
        results = {}
        
        # 分类（如果未分类或强制分类）
        if not email.category or force_classify:
            classification_service = ClassificationService()
            category, confidence = classification_service.classify_email(email)
            if category:
                email.category = category
                email.classification_confidence = confidence
                db.commit()
                results["classified"] = True
                results["category"] = category.value
                log.info(f"邮件 {email_id} 分类为: {category.value}")
        
        return {"success": True, **results}

    except Exception as e:
        log.error(f"处理邮件失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def generate_draft(self, email_id: int, tone: str = "professional", length: str = "medium"):
    """生成草稿"""
    db = self.db
    try:
        email = crud.get_email(db, email_id)
        if not email:
            return {"success": False, "message": "邮件不存在"}
        
        classification_service = ClassificationService()
        draft_body = classification_service.generate_draft(email, tone, length)
        
        if not draft_body:
            return {"success": False, "message": "生成草稿失败"}
        
        # 创建草稿记录
        from backend.db.schemas import DraftCreate
        draft = crud.create_draft(
            db,
            DraftCreate(
                email_id=email_id,
                subject=f"Re: {email.subject}" if email.subject else "回复",
                body=draft_body
            )
        )
        
        # 在邮箱中创建草稿
        account = email.account
        if account.provider == models.EmailProvider.GMAIL:
            service = GmailService(account)
            draft_id = service.create_draft(
                to=email.sender_email,
                subject=draft.subject,
                body=draft.body,
                thread_id=email.thread_id
            )
            if draft_id:
                draft.provider_draft_id = draft_id
                db.commit()
        else:
            log.warning(f"不支持的邮箱提供商: {account.provider}，无法创建草稿")
        
        log.info(f"为邮件 {email_id} 生成草稿: {draft.id}")
        return {"success": True, "draft_id": draft.id}
        
    except Exception as e:
        log.error(f"生成草稿失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def sync_email_status(self, account_id: int):
    """同步账户中所有邮件的已读/未读状态和删除状态（从Gmail同步到数据库）
    
    Args:
        account_id: 邮箱账户ID
    """
    db = self.db
    try:
        account = crud.get_email_account(db, account_id)
        if not account or not account.is_active:
            log.warning(f"邮箱账户 {account_id} 不存在或未激活")
            return {"success": False, "message": "账户不存在或未激活"}
        
        if account.provider != models.EmailProvider.GMAIL:
            return {"success": False, "message": "目前仅支持Gmail"}
        
        service = GmailService(account)
        
        # 获取账户的所有邮件
        emails = db.query(models.Email).filter(
            models.Email.account_id == account_id
        ).all()
        
        total_emails = len(emails)
        synced_count = 0
        updated_count = 0
        deleted_count = 0
        
        # 更新任务状态：开始处理
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': total_emails,
                'percent': 0,
                'synced_count': 0,
                'updated_count': 0,
                'deleted_count': 0,
                'status': '开始同步状态...'
            }
        )
        
        for idx, email in enumerate(emails, 1):
            try:
                # 首先检查邮件是否还存在
                exists = service.check_message_exists(email.provider_message_id)
                if not exists:
                    # 邮件在Gmail中已删除，标记为已删除
                    from backend.db.models import EmailStatus
                    if email.status != EmailStatus.DELETED:
                        crud.update_email(db, email.id, status=EmailStatus.DELETED)
                        deleted_count += 1
                        log.info(f"邮件 {email.id} 在Gmail中已删除，已标记为DELETED")
                    synced_count += 1
                    continue
                
                # 邮件存在，同步状态
                gmail_status = service.get_message_status(email.provider_message_id)
                if gmail_status:
                    from backend.db.models import EmailStatus
                    if gmail_status == 'unread':
                        db_status = EmailStatus.UNREAD
                    else:
                        db_status = EmailStatus.READ
                    
                    # 如果状态不一致，更新数据库
                    if email.status != db_status:
                        crud.update_email(db, email.id, status=db_status)
                        updated_count += 1
                    
                    synced_count += 1
                    
                    # 每处理20封邮件更新一次进度
                    if idx % 20 == 0 or idx == total_emails:
                        percent = idx * 100 // total_emails if total_emails > 0 else 100
                        self.update_state(
                            state='PROGRESS',
                            meta={
                                'current': idx,
                                'total': total_emails,
                                'percent': percent,
                                'synced_count': synced_count,
                                'updated_count': updated_count,
                                'deleted_count': deleted_count,
                                'status': f'同步中: {idx}/{total_emails} ({percent}%)'
                            }
                        )
            except Exception as e:
                log.warning(f"同步邮件 {email.id} 状态失败: {e}")
        
        log.info(f"账户 {account_id} 状态同步完成: 检查 {synced_count} 封，更新 {updated_count} 封，删除 {deleted_count} 封")
        
        # 更新任务状态：完成
        self.update_state(
            state='SUCCESS',
            meta={
                'current': total_emails,
                'total': total_emails,
                'percent': 100,
                'synced_count': synced_count,
                'updated_count': updated_count,
                'deleted_count': deleted_count,
                'status': '同步完成'
            }
        )
        
        return {
            "success": True,
            "synced_count": synced_count,
            "updated_count": updated_count,
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        log.error(f"同步邮件状态失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def check_all_accounts(self):
    """检查所有活跃账户的新邮件"""
    db = self.db
    try:
        accounts = crud.get_active_email_accounts(db)
        results = []
        
        for account in accounts:
            result = fetch_emails_from_account.delay(account.id)
            results.append({"account_id": account.id, "task_id": result.id})
        
        log.info(f"触发 {len(accounts)} 个账户的邮件检查任务")
        return {"success": True, "accounts": results}
        
    except Exception as e:
        log.error(f"检查所有账户失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def delete_email(self, email_id: int):
    """删除单封邮件（带延迟以避免限流）
    
    Args:
        email_id: 邮件ID
    """
    import time
    db = self.db
    try:
        email = crud.get_email(db, email_id)
        if not email:
            log.warning(f"邮件 {email_id} 不存在")
            return {"success": False, "message": "邮件不存在"}
        
        # 从Gmail删除
        account = email.account
        if account.provider == models.EmailProvider.GMAIL:
            service = GmailService(account)
            try:
                # 延迟0.1秒以避免限流
                time.sleep(0.1)
                success = service.delete_message(email.provider_message_id)
                if not success:
                    return {"success": False, "message": "Gmail删除失败"}
            except Exception as e:
                error_msg = str(e)
                log.error(f"删除Gmail邮件失败: {e}")
                # 如果是权限错误，返回更友好的提示
                if "权限不足" in error_msg or "insufficientPermissions" in error_msg or "Insufficient Permission" in error_msg:
                    return {
                        "success": False, 
                        "message": "权限不足：需要重新授权Gmail账户以获取删除邮件的权限。请在前端断开连接后重新连接。",
                        "requires_reauth": True
                    }
                return {"success": False, "message": str(e)}
        else:
            log.warning(f"不支持的邮箱提供商: {account.provider}")
            return {"success": False, "message": "不支持的邮箱提供商"}
        
        # 保存邮件ID用于后续清理
        provider_message_id = email.provider_message_id
        
        # 1. 先从向量存储删除（必须在数据库删除之前，避免检索到已删除的邮件）
        try:
            from backend.services.vector_store import VectorStoreService
            vector_store = VectorStoreService()
            vector_store.delete_email(email_id)
            log.info(f"邮件 {email_id} 已从向量存储删除")
        except Exception as e:
            log.warning(f"从向量存储删除邮件失败: {e}")
            # 继续执行，不因为向量删除失败而阻止整个删除流程
        
        # 2. 从数据库删除（级联删除会处理相关数据：drafts, email_embeddings等）
        db.delete(email)
        db.commit()
        log.info(f"邮件 {email_id} 已从数据库删除")
        
        log.info(f"邮件 {email_id} 删除成功")
        return {"success": True, "email_id": email_id}
        
    except Exception as e:
        log.error(f"删除邮件失败: {e}", exc_info=True)
        db.rollback()
        return {"success": False, "message": str(e)}


@celery_app.task(base=DatabaseTask, bind=True)
def delete_emails_batch(self, email_ids: List[int]):
    """批量删除邮件（使用队列逐个删除以避免限流）
    
    Args:
        email_ids: 邮件ID列表
    
    注意：每个删除任务之间间隔至少0.1秒，以避免Gmail API限流
    """
    db = self.db
    try:
        total = len(email_ids)
        success_count = 0
        failed_count = 0
        failed_ids = []
        
        log.info(f"开始批量删除 {total} 封邮件，将逐个提交删除任务（间隔0.1秒）")
        
        # 逐个删除，每个删除任务之间间隔0.1秒
        # countdown参数单位是秒，但Celery不支持小数，所以使用整数秒
        # 为了更精确的延迟，我们在delete_email任务内部使用time.sleep(0.1)
        for idx, email_id in enumerate(email_ids):
            try:
                # 使用apply_async并设置countdown来实现延迟
                # 每个任务延迟 idx * 0.2 秒（0.2秒 = 200毫秒，确保有足够间隔）
                # 这样即使有误差，也能保证至少0.1秒的间隔
                delete_email.apply_async(
                    args=[email_id],
                    countdown=idx * 0.2  # 0.2秒间隔，确保至少0.1秒
                )
                success_count += 1
            except Exception as e:
                log.error(f"提交删除任务失败 {email_id}: {e}")
                failed_count += 1
                failed_ids.append(email_id)
        
        log.info(f"批量删除任务已提交: 成功 {success_count}, 失败 {failed_count}")
        return {
            "success": True,
            "total": total,
            "submitted": success_count,
            "failed": failed_count,
            "failed_ids": failed_ids,
            "message": f"已提交 {success_count} 个删除任务，将在后台逐个执行（间隔0.2秒）"
        }
        
    except Exception as e:
        log.error(f"批量删除邮件失败: {e}", exc_info=True)
        return {"success": False, "message": str(e)}

