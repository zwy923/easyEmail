"""Email authentication related routes."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from backend.db import crud, models
from backend.db.database import get_db
from backend.db.schemas import ConnectEmailRequest
from backend.services.gmail_service import GmailService
from backend.tasks.email_tasks import fetch_emails_from_account
from backend.utils.logging_config import log
from backend.utils.oauth_utils import generate_state, get_gmail_auth_url

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
        token_data = GmailService.exchange_code_for_token(code)

        if not token_data:
            raise HTTPException(status_code=400, detail="获取token失败")

        user_email = token_data.get("email")
        if not user_email:
            log.error("token_data中缺少email字段")
            raise HTTPException(status_code=500, detail="无法获取用户邮箱地址")

        user = crud.get_user_by_email(db, user_email)
        if not user:
            from backend.db.schemas import UserCreate
            user = crud.create_user(db, UserCreate(email=user_email))

        existing_accounts = crud.get_email_accounts_by_user(db, user.id)
        account = None
        for acc in existing_accounts:
            if acc.email == user_email and acc.provider == models.EmailProvider.GMAIL:
                account = acc
                break

        if account:
            crud.update_email_account_token(
                db,
                account.id,
                token_data["access_token"],
                token_data.get("refresh_token"),
                token_data.get("expires_at")
            )
        else:
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

        fetch_emails_from_account.delay(account.id)

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset=\"UTF-8\">
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
            <div class=\"container\">
                <div class=\"success\">✓ 连接成功！</div>
                <div class=\"message\">Gmail账户 ({user_email}) 已成功连接</div>
                <div class=\"message\">窗口将在3秒后自动关闭...</div>
            </div>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'gmail_connected', success: true }}, '*');
                }}
                setTimeout(function() {{
                    window.close();
                }}, 3000);
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)

    except Exception as exc:
        log.error(f"Gmail OAuth回调处理失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"连接失败: {str(exc)}")


@router.post("/connect")
async def connect_email(
    request: ConnectEmailRequest,
    db: Session = Depends(get_db)
):
    """连接邮箱账户（手动连接，使用授权码）"""
    try:
        if request.provider == models.EmailProvider.GMAIL:
            token_data = GmailService.exchange_code_for_token(request.code)
        else:
            raise HTTPException(status_code=400, detail="不支持的提供商，目前仅支持Gmail")

        if not token_data:
            raise HTTPException(status_code=400, detail="获取token失败")

        user_email = token_data["email"]
        user = crud.get_user_by_email(db, user_email)
        if not user:
            from backend.db.schemas import UserCreate
            user = crud.create_user(db, UserCreate(email=user_email))

        existing_accounts = crud.get_email_accounts_by_user(db, user.id)
        account = None
        for acc in existing_accounts:
            if acc.email == user_email and acc.provider == request.provider:
                account = acc
                break

        if account:
            crud.update_email_account_token(
                db,
                account.id,
                token_data["access_token"],
                token_data.get("refresh_token"),
                token_data.get("expires_at")
            )
        else:
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

        fetch_emails_from_account.delay(account.id)

        return {"success": True, "account_id": account.id}

    except Exception as exc:
        log.error(f"连接邮箱失败: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
