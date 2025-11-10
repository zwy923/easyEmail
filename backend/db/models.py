"""SQLAlchemy数据库模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from datetime import datetime
import enum

from backend.db.database import Base


class EmailProvider(str, enum.Enum):
    """邮箱提供商"""
    GMAIL = "gmail"


class EmailStatus(str, enum.Enum):
    """邮件状态"""
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ClassificationCategory(str, enum.Enum):
    """分类类别"""
    URGENT = "urgent"
    IMPORTANT = "important"
    NORMAL = "normal"
    SPAM = "spam"
    PROMOTION = "promotion"


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    email_accounts = relationship("EmailAccount", back_populates="user", cascade="all, delete-orphan")


class EmailAccount(Base):
    """邮箱账户表"""
    __tablename__ = "email_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(SQLEnum(EmailProvider), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    access_token = Column(Text)  # 加密存储
    refresh_token = Column(Text)  # 加密存储
    token_expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    user = relationship("User", back_populates="email_accounts")
    emails = relationship("Email", back_populates="account", cascade="all, delete-orphan")


class Email(Base):
    """邮件表"""
    __tablename__ = "emails"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    provider_message_id = Column(String(512), unique=True, nullable=False, index=True)
    thread_id = Column(String(512), index=True)
    subject = Column(String(512))
    sender = Column(String(255), index=True)
    sender_email = Column(String(255), index=True)
    recipients = Column(JSON)  # 收件人列表
    cc = Column(JSON)  # CC列表
    bcc = Column(JSON)  # BCC列表
    body_text = Column(Text)
    body_html = Column(Text)
    received_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(SQLEnum(EmailStatus), default=EmailStatus.UNREAD)
    category = Column(SQLEnum(ClassificationCategory))
    classification_confidence = Column(Integer)  # 0-100
    is_important = Column(Boolean, default=False)
    labels = Column(JSON)  # 标签列表
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    account = relationship("EmailAccount", back_populates="emails")
    drafts = relationship("Draft", back_populates="email", cascade="all, delete-orphan")


class Draft(Base):
    """草稿表"""
    __tablename__ = "drafts"
    
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False)
    subject = Column(String(512))
    body = Column(Text, nullable=False)
    provider_draft_id = Column(String(512))  # 邮箱提供商的草稿ID
    is_sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    email = relationship("Email", back_populates="drafts")


class EmailEmbedding(Base):
    """邮件向量嵌入表"""
    __tablename__ = "email_embeddings"
    
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False, unique=True, index=True)
    embedding = Column(Text)  # pgvector向量数据（存储为文本，实际使用pgvector类型）
    meta_data = Column("metadata", JSON)  # 元数据（邮件摘要、关键词等），数据库列名仍为metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系（一对一关系：一个邮件对应一个嵌入记录）
    # 注意：cascade 在 backref 中设置，使用 single_parent=True 允许 delete-orphan
    email = relationship("Email", backref=backref("embedding", uselist=False, cascade="all, delete-orphan", single_parent=True))

