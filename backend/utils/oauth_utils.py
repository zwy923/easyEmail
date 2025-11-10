"""OAuth2辅助函数"""
from typing import Optional
from datetime import datetime, timedelta
import secrets
import hashlib
import base64

from backend.config import settings
from backend.utils.logging_config import log


def generate_state() -> str:
    """生成OAuth state参数（用于防止CSRF攻击）"""
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    """生成PKCE code verifier"""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')


def generate_code_challenge(verifier: str) -> str:
    """生成PKCE code challenge"""
    sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')


def is_token_expired(expires_at: Optional[datetime]) -> bool:
    """检查token是否过期"""
    if not expires_at:
        return True
    
    # 提前5分钟刷新
    return datetime.utcnow() >= (expires_at - timedelta(minutes=5))


def encrypt_token(token: str) -> str:
    """加密token（简单实现，生产环境应使用更强的加密）"""
    # 这里使用简单的base64编码，生产环境应使用AES加密
    # 注意：这只是示例，实际应用中应使用加密库如cryptography
    return base64.b64encode(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """解密token"""
    try:
        return base64.b64decode(encrypted_token.encode()).decode()
    except Exception as e:
        log.error(f"解密token失败: {e}")
        return ""


# Gmail OAuth URL生成
def get_gmail_auth_url(state: str) -> str:
    """生成Gmail OAuth授权URL"""
    from google_auth_oauthlib.flow import Flow
    from google.oauth2.credentials import Credentials
    
    scopes = [
        'openid',  # Google OAuth 会自动添加，显式包含以避免scope不匹配
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/gmail.compose',
        'https://www.googleapis.com/auth/userinfo.email'  # 获取用户email
    ]
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GMAIL_REDIRECT_URI]
            }
        },
        scopes=scopes,
        redirect_uri=settings.GMAIL_REDIRECT_URI
    )
    
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        state=state,
        prompt='consent'  # 强制显示同意页面以获取refresh_token
    )
    
    return auth_url

