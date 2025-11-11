"""Routes for managing email accounts."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db import models
from backend.db.database import get_db
from backend.db.schemas import EmailAccountResponse

router = APIRouter()


@router.get("/accounts", response_model=list[EmailAccountResponse])
async def get_email_accounts(db: Session = Depends(get_db)):
    """获取所有邮箱账户"""
    accounts: list[EmailAccountResponse] = []
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
