"""Celery异步任务定义"""
from celery import Task
from typing import List, Dict
from datetime import datetime

from backend.celery_worker import celery_app
from backend.utils.logging_config import log
from backend.db.database import SessionLocal
from backend.db import crud, models
from backend.services.gmail_service import GmailService
from backend.services.classification_service import ClassificationService
from backend.services.rule_engine import RuleEngine


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
        
        for idx, msg in enumerate(messages, 1):
            # 每处理50封邮件记录一次进度
            if idx % 50 == 0:
                log.info(f"处理进度: {idx}/{total_messages} ({idx*100//total_messages}%), 新增: {new_count}, 跳过: {skipped_count}, 错误: {error_count}")
            
            message_id = msg.get("id")
            
            # 检查邮件是否已存在
            existing = crud.get_email_by_provider_id(db, message_id)
            if existing:
                skipped_count += 1
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
                labels=email_data.get("labels", [])
            )
            
            email = crud.create_email(db, email_create)
            new_count += 1
            
            # 添加到向量存储
            try:
                from backend.services.vector_store import VectorStoreService
                vector_store = VectorStoreService()
                vector_store.add_email(email)
            except Exception as e:
                log.warning(f"添加邮件到向量存储失败: {e}")
            
            # 异步处理邮件（分类和规则）
            process_email.delay(email.id)
        
        log.info(f"账户 {account_id} 处理完成: 总计 {total_messages} 封，新增 {new_count} 封，跳过 {skipped_count} 封，错误 {error_count} 封")
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
    """处理邮件：分类和规则匹配"""
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
        
        # 规则匹配
        try:
            rule_engine = RuleEngine()
            rule_results = rule_engine.process_email_with_rules(email, db)
            results["rules_matched"] = len(rule_results)
            results["rule_results"] = rule_results
        except Exception as rule_error:
            log.error(f"规则匹配失败: {rule_error}", exc_info=True)
            results["rules_matched"] = 0
            results["rule_results"] = []
            results["rule_error"] = str(rule_error)
        
        # 记录日志
        try:
            crud.create_log(
                db,
                level="INFO",
                message=f"处理邮件 {email_id}",
                module="email_tasks",
                action="process_email",
                details=results
            )
        except Exception as log_error:
            log.warning(f"记录日志失败: {log_error}")
        
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
                log.error(f"删除Gmail邮件失败: {e}")
                return {"success": False, "message": str(e)}
        else:
            log.warning(f"不支持的邮箱提供商: {account.provider}")
            return {"success": False, "message": "不支持的邮箱提供商"}
        
        # 从向量存储删除
        try:
            from backend.services.vector_store import VectorStoreService
            vector_store = VectorStoreService()
            vector_store.delete_email(email_id)
        except Exception as e:
            log.warning(f"从向量存储删除邮件失败: {e}")
        
        # 从数据库删除（级联删除会处理相关数据）
        db.delete(email)
        db.commit()
        
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

