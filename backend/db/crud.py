"""数据库CRUD操作"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from typing import List, Optional
from datetime import datetime

from backend.db import models, schemas


# ========== 用户CRUD ==========
def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """创建用户"""
    db_user = models.User(**user.dict())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """通过邮箱获取用户"""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user(db: Session, user_id: int) -> Optional[models.User]:
    """获取用户"""
    return db.query(models.User).filter(models.User.id == user_id).first()


# ========== 邮箱账户CRUD ==========
def create_email_account(db: Session, account: schemas.EmailAccountCreate, user_id: int) -> models.EmailAccount:
    """创建邮箱账户"""
    db_account = models.EmailAccount(
        user_id=user_id,
        **account.dict()
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


def get_email_account(db: Session, account_id: int) -> Optional[models.EmailAccount]:
    """获取邮箱账户"""
    return db.query(models.EmailAccount).filter(models.EmailAccount.id == account_id).first()


def get_email_accounts_by_user(db: Session, user_id: int) -> List[models.EmailAccount]:
    """获取用户的所有邮箱账户"""
    return db.query(models.EmailAccount).filter(models.EmailAccount.user_id == user_id).all()


def get_active_email_accounts(db: Session) -> List[models.EmailAccount]:
    """获取所有活跃的邮箱账户"""
    return db.query(models.EmailAccount).filter(models.EmailAccount.is_active == True).all()


def update_email_account_token(
    db: Session,
    account_id: int,
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_at: Optional[datetime] = None
) -> models.EmailAccount:
    """更新邮箱账户token"""
    account = get_email_account(db, account_id)
    if account:
        account.access_token = access_token
        if refresh_token:
            account.refresh_token = refresh_token
        if expires_at:
            account.token_expires_at = expires_at
        db.commit()
        db.refresh(account)
    return account


# ========== 邮件CRUD ==========
def create_email(db: Session, email: schemas.EmailCreate) -> models.Email:
    """创建邮件记录"""
    db_email = models.Email(**email.dict())
    db.add(db_email)
    db.commit()
    db.refresh(db_email)
    return db_email


def get_email(db: Session, email_id: int) -> Optional[models.Email]:
    """获取邮件"""
    return db.query(models.Email).filter(models.Email.id == email_id).first()


def get_email_by_provider_id(db: Session, provider_message_id: str) -> Optional[models.Email]:
    """通过提供商消息ID获取邮件"""
    return db.query(models.Email).filter(
        models.Email.provider_message_id == provider_message_id
    ).first()


def get_emails(
    db: Session,
    account_id: Optional[int] = None,
    status: Optional[models.EmailStatus] = None,
    category: Optional[models.ClassificationCategory] = None,
    sender: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    exclude_deleted: bool = True  # 默认排除已删除的邮件
) -> tuple[List[models.Email], int]:
    """获取邮件列表（带分页）
    
    Args:
        exclude_deleted: 是否排除已删除的邮件（默认True）
    """
    query = db.query(models.Email)
    
    if account_id:
        query = query.filter(models.Email.account_id == account_id)
    if status:
        query = query.filter(models.Email.status == status)
    elif exclude_deleted:
        # 默认排除已删除的邮件
        query = query.filter(models.Email.status != models.EmailStatus.DELETED)
    if category:
        query = query.filter(models.Email.category == category)
    if sender:
        query = query.filter(
            or_(
                models.Email.sender.contains(sender),
                models.Email.sender_email.contains(sender)
            )
        )
    
    total = query.count()
    items = query.order_by(desc(models.Email.received_at)).offset(offset).limit(limit).all()
    
    return items, total


def update_email(db: Session, email_id: int, **kwargs) -> Optional[models.Email]:
    """更新邮件
    
    注意：如果更新了影响向量内容的字段（subject, body_text, body_html, sender等），
    会自动更新向量存储
    """
    email = get_email(db, email_id)
    if email:
        # 记录哪些字段被更新了
        updated_fields = set(kwargs.keys())
        
        # 定义影响向量内容的字段
        vector_content_fields = {
            'subject', 'body_text', 'body_html', 
            'sender', 'sender_email'
        }
        
        # 检查是否有影响向量的字段被更新
        needs_vector_update = bool(updated_fields & vector_content_fields)
        
        for key, value in kwargs.items():
            if hasattr(email, key):
                setattr(email, key, value)
        db.commit()
        db.refresh(email)
        
        # 如果更新了影响向量的字段，更新向量存储
        if needs_vector_update:
            try:
                from backend.services.vector_store import VectorStoreService
                vector_store = VectorStoreService()
                vector_store.update_email(email)
                log.debug(f"邮件 {email_id} 的向量已更新（字段: {updated_fields & vector_content_fields}）")
            except Exception as e:
                log.warning(f"更新邮件 {email_id} 向量失败: {e}")
        
    return email


# ========== 规则CRUD ==========
def create_rule(db: Session, rule: schemas.RuleCreate) -> models.Rule:
    """创建规则"""
    db_rule = models.Rule(
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        priority=rule.priority,
        conditions=rule.conditions.dict(),
        actions=rule.actions.dict()
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def get_rule(db: Session, rule_id: int) -> Optional[models.Rule]:
    """获取规则"""
    return db.query(models.Rule).filter(models.Rule.id == rule_id).first()


def get_rules(db: Session, is_active: Optional[bool] = None) -> List[models.Rule]:
    """获取规则列表"""
    query = db.query(models.Rule)
    if is_active is not None:
        query = query.filter(models.Rule.is_active == is_active)
    return query.order_by(desc(models.Rule.priority), desc(models.Rule.created_at)).all()


def update_rule(db: Session, rule_id: int, rule_update: schemas.RuleUpdate) -> Optional[models.Rule]:
    """更新规则"""
    rule = get_rule(db, rule_id)
    if rule:
        update_data = rule_update.dict(exclude_unset=True)
        if "conditions" in update_data and update_data["conditions"]:
            update_data["conditions"] = update_data["conditions"].dict()
        if "actions" in update_data and update_data["actions"]:
            update_data["actions"] = update_data["actions"].dict()
        
        for key, value in update_data.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        db.commit()
        db.refresh(rule)
    return rule


def delete_rule(db: Session, rule_id: int) -> bool:
    """删除规则"""
    rule = get_rule(db, rule_id)
    if rule:
        db.delete(rule)
        db.commit()
        return True
    return False


def increment_rule_match_count(db: Session, rule_id: int) -> Optional[models.Rule]:
    """增加规则匹配次数"""
    rule = get_rule(db, rule_id)
    if rule:
        rule.match_count += 1
        rule.last_matched_at = datetime.utcnow()
        db.commit()
        db.refresh(rule)
    return rule


# ========== 草稿CRUD ==========
def create_draft(db: Session, draft: schemas.DraftCreate) -> models.Draft:
    """创建草稿"""
    db_draft = models.Draft(**draft.dict())
    db.add(db_draft)
    db.commit()
    db.refresh(db_draft)
    return db_draft


def get_draft(db: Session, draft_id: int) -> Optional[models.Draft]:
    """获取草稿"""
    return db.query(models.Draft).filter(models.Draft.id == draft_id).first()


def get_drafts_by_email(db: Session, email_id: int) -> List[models.Draft]:
    """获取邮件的所有草稿"""
    return db.query(models.Draft).filter(models.Draft.email_id == email_id).all()


def update_draft(db: Session, draft_id: int, **kwargs) -> Optional[models.Draft]:
    """更新草稿"""
    draft = get_draft(db, draft_id)
    if draft:
        for key, value in kwargs.items():
            if hasattr(draft, key):
                setattr(draft, key, value)
        db.commit()
        db.refresh(draft)
    return draft


# ========== 日志CRUD ==========
def create_log(
    db: Session,
    level: str,
    message: str,
    module: Optional[str] = None,
    action: Optional[str] = None,
    details: Optional[dict] = None
) -> models.Log:
    """创建日志"""
    db_log = models.Log(
        level=level,
        module=module,
        action=action,
        message=message,
        details=details
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return db_log


def get_logs(
    db: Session,
    level: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> tuple[List[models.Log], int]:
    """获取日志列表"""
    query = db.query(models.Log)
    if level:
        query = query.filter(models.Log.level == level)
    
    total = query.count()
    items = query.order_by(desc(models.Log.created_at)).offset(offset).limit(limit).all()
    
    return items, total

