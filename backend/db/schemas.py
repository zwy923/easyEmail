"""Pydantic模型（请求/响应验证）"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from backend.db.models import EmailProvider, EmailStatus, ClassificationCategory, RuleAction


# ========== 用户相关 ==========
class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}


# ========== 邮箱账户相关 ==========
class EmailAccountBase(BaseModel):
    provider: EmailProvider
    email: EmailStr


class EmailAccountCreate(EmailAccountBase):
    access_token: str
    refresh_token: str
    token_expires_at: Optional[datetime] = None


class EmailAccountResponse(EmailAccountBase):
    id: int
    user_id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


# ========== 邮件相关 ==========
class EmailBase(BaseModel):
    subject: Optional[str] = None
    sender: Optional[str] = None
    sender_email: Optional[str] = None


class EmailCreate(EmailBase):
    account_id: int
    provider_message_id: str
    thread_id: Optional[str] = None
    recipients: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    received_at: datetime
    status: EmailStatus = EmailStatus.UNREAD
    labels: Optional[List[str]] = None


class EmailResponse(EmailBase):
    id: int
    account_id: int
    provider_message_id: str
    thread_id: Optional[str] = None
    recipients: Optional[List[str]] = None
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    received_at: datetime
    status: EmailStatus
    category: Optional[ClassificationCategory] = None
    classification_confidence: Optional[int] = None
    is_important: bool
    labels: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class EmailListResponse(BaseModel):
    """邮件列表响应"""
    total: int
    items: List[EmailResponse]


# ========== 规则相关 ==========
class RuleCondition(BaseModel):
    """规则条件"""
    sender: Optional[Dict[str, Any]] = None
    subject: Optional[Dict[str, Any]] = None
    body: Optional[Dict[str, Any]] = None
    date_range: Optional[Dict[str, Any]] = None


class RuleActionConfig(BaseModel):
    """规则动作配置"""
    type: RuleAction
    category: Optional[ClassificationCategory] = None
    mark_important: Optional[bool] = False
    generate_draft: Optional[bool] = False
    forward_to: Optional[str] = None
    remind_after_hours: Optional[int] = None


class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True
    priority: int = 0
    conditions: RuleCondition
    actions: RuleActionConfig


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    conditions: Optional[RuleCondition] = None
    actions: Optional[RuleActionConfig] = None


class RuleResponse(RuleBase):
    id: int
    match_count: int
    last_matched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


# ========== 草稿相关 ==========
class DraftBase(BaseModel):
    subject: Optional[str] = None
    body: str


class DraftCreate(DraftBase):
    email_id: int


class DraftResponse(DraftBase):
    id: int
    email_id: int
    provider_draft_id: Optional[str] = None
    is_sent: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


# ========== 日志相关 ==========
class LogResponse(BaseModel):
    id: int
    level: str
    module: Optional[str] = None
    action: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}


# ========== API请求/响应 ==========
class ClassifyRequest(BaseModel):
    """分类请求"""
    email_id: int
    force: bool = False  # 是否强制重新分类


class DraftRequest(BaseModel):
    """生成草稿请求"""
    email_id: int
    tone: Optional[str] = "professional"  # professional, friendly, formal
    length: Optional[str] = "medium"  # short, medium, long


class ConnectEmailRequest(BaseModel):
    """连接邮箱请求"""
    provider: EmailProvider
    code: str  # OAuth授权码


class EmailListQuery(BaseModel):
    """邮件列表查询参数"""
    account_id: Optional[int] = None
    status: Optional[EmailStatus] = None
    category: Optional[ClassificationCategory] = None
    sender: Optional[str] = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

