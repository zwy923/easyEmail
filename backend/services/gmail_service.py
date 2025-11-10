"""Gmail API服务"""
from typing import List, Dict, Optional
from datetime import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
import email

from backend.config import settings
from backend.utils.logging_config import log
from backend.utils.mail_parser import parse_email_message
from backend.db.models import EmailAccount


class GmailService:
    """Gmail服务类"""
    
    def __init__(self, account: EmailAccount):
        self.account = account
        self.service = None
        self._build_service()
    
    def _build_service(self):
        """构建Gmail API服务"""
        try:
            creds = self._get_credentials()
            if creds and creds.valid:
                self.service = build('gmail', 'v1', credentials=creds)
            else:
                log.error(f"Gmail账户 {self.account.email} 的凭证无效")
        except Exception as e:
            log.error(f"构建Gmail服务失败: {e}")
    
    def _get_credentials(self) -> Optional[Credentials]:
        """获取并刷新凭证"""
        try:
            # 从数据库获取token（这里假设已解密）
            creds = Credentials(
                token=self.account.access_token,
                refresh_token=self.account.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GMAIL_CLIENT_ID,
                client_secret=settings.GMAIL_CLIENT_SECRET
            )
            
            # 如果token过期，刷新
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # 更新数据库中的token
                # 这里应该在调用方更新数据库
                return creds
            
            return creds
        except Exception as e:
            log.error(f"获取Gmail凭证失败: {e}")
            return None
    
    def refresh_token(self) -> bool:
        """刷新token并更新数据库"""
        try:
            creds = self._get_credentials()
            if creds:
                # 更新数据库
                from backend.db.database import SessionLocal
                db = SessionLocal()
                try:
                    self.account.access_token = creds.token
                    if creds.refresh_token:
                        self.account.refresh_token = creds.refresh_token
                    if creds.expiry:
                        self.account.token_expires_at = creds.expiry
                    db.commit()
                    # 重新构建服务
                    self._build_service()
                    return True
                finally:
                    db.close()
            return False
        except Exception as e:
            log.error(f"刷新Gmail token失败: {e}")
            return False
    
    def get_messages(self, max_results: int = None, query: str = "", fetch_all: bool = False) -> List[Dict]:
        """获取邮件列表
        
        Args:
            max_results: 最大返回数量（如果为None且fetch_all=False，默认50）
            query: 查询条件
            fetch_all: 是否获取所有邮件（忽略max_results限制）
        
        Returns:
            邮件列表
        """
        if not self.service:
            if not self.refresh_token():
                return []
        
        try:
            all_messages = []
            page_token = None
            batch_size = 500  # Gmail API单次请求最大500条
            
            # 如果fetch_all为True，则获取所有邮件
            # 如果max_results为None，默认使用50（向后兼容）
            if max_results is None and not fetch_all:
                max_results = 50
            
            while True:
                # 计算本次请求的数量
                if fetch_all:
                    # 获取所有邮件时，每次请求500条
                    current_max = batch_size
                elif max_results:
                    # 计算还需要获取多少条
                    remaining = max_results - len(all_messages)
                    if remaining <= 0:
                        break
                    current_max = min(remaining, batch_size)
                else:
                    break
                
                # 构建请求参数
                request_params = {
                    'userId': 'me',
                    'maxResults': current_max,
                }
                if query:
                    request_params['q'] = query
                if page_token:
                    request_params['pageToken'] = page_token
                
                # 执行请求
                results = self.service.users().messages().list(**request_params).execute()
                
                messages = results.get('messages', [])
                all_messages.extend(messages)
                
                # 检查是否有下一页
                page_token = results.get('nextPageToken')
                if not page_token:
                    # 没有更多页面了
                    break
                
                # 如果设置了max_results且已获取足够数量，停止
                if max_results and len(all_messages) >= max_results:
                    all_messages = all_messages[:max_results]
                    break
                
                log.debug(f"已获取 {len(all_messages)} 封邮件，继续获取...")
            
            log.info(f"总共获取到 {len(all_messages)} 封邮件")
            return all_messages
            
        except HttpError as e:
            log.error(f"获取Gmail邮件列表失败: {e}")
            if e.resp.status == 401:
                # Token过期，尝试刷新
                if self.refresh_token():
                    return self.get_messages(max_results, query, fetch_all)
            return []
    
    def get_message(self, message_id: str) -> Optional[Dict]:
        """获取邮件详情"""
        if not self.service:
            if not self.refresh_token():
                return None
        
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='raw'
            ).execute()
            
            # 解析邮件
            raw_data = base64.urlsafe_b64decode(message['raw'])
            parsed = parse_email_message(raw_data)
            
            # 获取标签
            labels = message.get('labelIds', [])
            
            # 获取线程ID
            thread_id = message.get('threadId', '')
            
            # 获取时间戳
            internal_date = message.get('internalDate')
            received_at = None
            if internal_date:
                received_at = datetime.fromtimestamp(int(internal_date) / 1000)
            
            return {
                **parsed,
                "provider_message_id": message_id,
                "thread_id": thread_id,
                "labels": labels,
                "received_at": received_at or parsed.get("received_at")
            }
        except HttpError as e:
            log.error(f"获取Gmail邮件详情失败: {e}")
            if e.resp.status == 401:
                if self.refresh_token():
                    return self.get_message(message_id)
            return None
    
    def send_message(self, to: str, subject: str, body: str, is_html: bool = False) -> Optional[str]:
        """发送邮件"""
        if not self.service:
            if not self.refresh_token():
                return None
        
        try:
            # 构建邮件消息
            message = email.message.EmailMessage()
            message['To'] = to
            message['Subject'] = subject
            
            if is_html:
                message.set_content(body, subtype='html')
            else:
                message.set_content(body)
            
            # 编码为base64url
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            send_message = {
                'raw': raw_message
            }
            
            if thread_id:
                send_message['threadId'] = thread_id
            
            result = self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()
            
            log.info(f"Gmail邮件发送成功: {result.get('id')}")
            return result.get('id')
        except HttpError as e:
            log.error(f"发送Gmail邮件失败: {e}")
            if e.resp.status == 401:
                if self.refresh_token():
                    return self.send_message(to, subject, body, is_html)
            return None
    
    def create_draft(self, to: str, subject: str, body: str, thread_id: Optional[str] = None) -> Optional[str]:
        """创建草稿"""
        if not self.service:
            if not self.refresh_token():
                return None
        
        try:
            # 构建邮件消息
            message = email.message.EmailMessage()
            message['To'] = to
            message['Subject'] = subject
            message.set_content(body)
            
            # 编码为base64url
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            draft = {
                'message': {
                    'raw': raw_message
                }
            }
            
            if thread_id:
                draft['message']['threadId'] = thread_id
            
            result = self.service.users().drafts().create(
                userId='me',
                body=draft
            ).execute()
            
            draft_id = result.get('id')
            log.info(f"Gmail草稿创建成功: {draft_id}")
            return draft_id
        except HttpError as e:
            log.error(f"创建Gmail草稿失败: {e}")
            if e.resp.status == 401:
                if self.refresh_token():
                    return self.create_draft(to, subject, body, thread_id)
            return None
    
    def delete_draft(self, draft_id: str) -> bool:
        """删除草稿"""
        if not self.service:
            if not self.refresh_token():
                return False
        
        try:
            self.service.users().drafts().delete(
                userId='me',
                id=draft_id
            ).execute()
            log.info(f"Gmail草稿删除成功: {draft_id}")
            return True
        except HttpError as e:
            log.error(f"删除Gmail草稿失败: {e}")
            if e.resp.status == 401:
                if self.refresh_token():
                    return self.delete_draft(draft_id)
            return False
    
    def modify_message(self, message_id: str, add_labels: List[str] = None, remove_labels: List[str] = None) -> bool:
        """修改邮件（添加/删除标签）"""
        if not self.service:
            if not self.refresh_token():
                return False
        
        try:
            modify_request = {}
            if add_labels:
                modify_request['addLabelIds'] = add_labels
            if remove_labels:
                modify_request['removeLabelIds'] = remove_labels
            
            if modify_request:
                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body=modify_request
                ).execute()
                return True
            return False
        except HttpError as e:
            log.error(f"修改Gmail邮件失败: {e}")
            if e.resp.status == 401:
                if self.refresh_token():
                    return self.modify_message(message_id, add_labels, remove_labels)
            return False
    
    def mark_as_read(self, message_id: str) -> bool:
        """标记为已读"""
        return self.modify_message(message_id, remove_labels=['UNREAD'])
    
    def mark_as_important(self, message_id: str) -> bool:
        """标记为重要"""
        return self.modify_message(message_id, add_labels=['IMPORTANT'])
    
    def delete_message(self, message_id: str) -> bool:
        """删除邮件
        
        Args:
            message_id: Gmail消息ID
            
        Returns:
            是否成功
        """
        if not self.service:
            if not self.refresh_token():
                return False
        
        try:
            self.service.users().messages().delete(
                userId='me',
                id=message_id
            ).execute()
            log.info(f"Gmail邮件删除成功: {message_id}")
            return True
        except HttpError as e:
            log.error(f"删除Gmail邮件失败: {e}")
            if e.resp.status == 401:
                # Token过期，尝试刷新
                if self.refresh_token():
                    return self.delete_message(message_id)
            elif e.resp.status == 429:
                # 限流错误
                log.warning(f"Gmail API限流，邮件 {message_id} 删除失败")
                raise Exception("Gmail API限流，请稍后重试")
            return False
    
    @staticmethod
    def exchange_code_for_token(code: str) -> Optional[Dict]:
        """使用授权码交换token"""
        try:
            # 使用与授权URL生成时相同的scopes
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
            
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            # 获取用户信息（email）
            email = None
            try:
                session = flow.authorized_session()
                userinfo_response = session.get('https://www.googleapis.com/oauth2/v2/userinfo')
                if userinfo_response.status_code == 200:
                    userinfo = userinfo_response.json()
                    email = userinfo.get('email')
                    log.info(f"从userinfo获取到email: {email}")
            except Exception as e:
                log.warning(f"从userinfo获取email失败: {e}")
            
            # 如果无法从userinfo获取，尝试使用Gmail API获取profile
            if not email:
                try:
                    from googleapiclient.discovery import build
                    service = build('gmail', 'v1', credentials=creds)
                    profile = service.users().getProfile(userId='me').execute()
                    email = profile.get('emailAddress')
                    log.info(f"从Gmail profile获取到email: {email}")
                except Exception as e:
                    log.warning(f"从Gmail profile获取email失败: {e}")
            
            if not email:
                log.error("无法获取用户email")
                return None
            
            return {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "expires_at": creds.expiry,
                "email": email
            }
        except Exception as e:
            log.error(f"Gmail token交换失败: {e}")
            return None

