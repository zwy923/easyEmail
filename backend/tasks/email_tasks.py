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
        
        # 获取邮件列表
        messages = service.get_messages(max_results=50)
        new_count = 0
        
        for msg in messages:
            message_id = msg.get("id")
            
            # 检查邮件是否已存在
            existing = crud.get_email_by_provider_id(db, message_id)
            if existing:
                continue
            
            # 获取邮件详情
            email_data = service.get_message(message_id)
            if not email_data:
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
        
        log.info(f"账户 {account_id} 获取到 {new_count} 封新邮件")
        return {"success": True, "new_count": new_count}
        
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
        rule_engine = RuleEngine()
        rule_results = rule_engine.process_email_with_rules(email, db)
        results["rules_matched"] = len(rule_results)
        results["rule_results"] = rule_results
        
        # 记录日志
        crud.create_log(
            db,
            level="INFO",
            message=f"处理邮件 {email_id}",
            module="email_tasks",
            action="process_email",
            details=results
        )
        
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

