"""邮件解析工具"""
import email
from email.header import decode_header
from typing import Optional, Dict, List
import re
from html import unescape
from html.parser import HTMLParser


class HTMLTextExtractor(HTMLParser):
    """HTML文本提取器"""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_tags = ['script', 'style']
        self.in_skip_tag = False
    
    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.in_skip_tag = True
    
    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags:
            self.in_skip_tag = False
        elif tag.lower() in ['p', 'br', 'div']:
            self.text.append('\n')
    
    def handle_data(self, data):
        if not self.in_skip_tag:
            self.text.append(data)
    
    def get_text(self):
        return ''.join(self.text).strip()


def decode_mime_header(header: Optional[str]) -> str:
    """解码MIME头"""
    if not header:
        return ""
    
    decoded_parts = decode_header(header)
    decoded_string = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            try:
                decoded_string += part.decode(encoding or 'utf-8')
            except (UnicodeDecodeError, LookupError):
                decoded_string += part.decode('utf-8', errors='ignore')
        else:
            decoded_string += part
    return decoded_string


def parse_email_address(address: str) -> tuple[str, str]:
    """解析邮箱地址，返回(名称, 邮箱)"""
    if not address:
        return ("", "")
    
    # 解码MIME编码
    decoded = decode_mime_header(address)
    
    # 匹配格式: "Name <email@example.com>" 或 "email@example.com"
    match = re.match(r'^(.+?)\s*<(.+?)>$', decoded)
    if match:
        name = match.group(1).strip().strip('"\'')
        email_addr = match.group(2).strip()
        return (name, email_addr)
    else:
        # 直接是邮箱地址
        return ("", decoded.strip())


def parse_address_list(address_list: Optional[str]) -> List[Dict[str, str]]:
    """解析地址列表"""
    if not address_list:
        return []
    
    result = []
    # 分割多个地址（考虑逗号和分号）
    addresses = re.split(r'[,;]', address_list)
    
    for addr in addresses:
        addr = addr.strip()
        if addr:
            name, email = parse_email_address(addr)
            result.append({"name": name, "email": email})
    
    return result


def extract_text_from_html(html_content: str) -> str:
    """从HTML中提取纯文本"""
    if not html_content:
        return ""
    
    extractor = HTMLTextExtractor()
    extractor.feed(html_content)
    text = extractor.get_text()
    
    # 清理多余的空白
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()


def parse_email_message(message_data: bytes) -> Dict:
    """解析邮件消息"""
    msg = email.message_from_bytes(message_data)
    
    # 解析头部
    subject = decode_mime_header(msg.get("Subject", ""))
    sender = decode_mime_header(msg.get("From", ""))
    sender_name, sender_email = parse_email_address(sender)
    
    # 解析收件人
    to_list = parse_address_list(msg.get("To", ""))
    cc_list = parse_address_list(msg.get("Cc", ""))
    bcc_list = parse_address_list(msg.get("Bcc", ""))
    
    # 解析日期
    date_str = msg.get("Date", "")
    received_at = None
    if date_str:
        try:
            received_at = email.utils.parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            pass
    
    # 解析正文
    body_text = ""
    body_html = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # 跳过附件
            if "attachment" in content_disposition:
                continue
            
            if content_type == "text/plain" and not body_text:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body_text = payload.decode(charset, errors='ignore')
                except Exception:
                    pass
            
            elif content_type == "text/html" and not body_html:
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body_html = payload.decode(charset, errors='ignore')
                    # 如果没有纯文本，从HTML提取
                    if not body_text:
                        body_text = extract_text_from_html(body_html)
                except Exception:
                    pass
    else:
        # 单部分消息
        content_type = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            content = payload.decode(charset, errors='ignore')
            
            if content_type == "text/html":
                body_html = content
                body_text = extract_text_from_html(content)
            else:
                body_text = content
        except Exception:
            pass
    
    return {
        "subject": subject,
        "sender": sender_name if sender_name else sender_email,
        "sender_email": sender_email,
        "recipients": [addr["email"] for addr in to_list],
        "cc": [addr["email"] for addr in cc_list],
        "bcc": [addr["email"] for addr in bcc_list],
        "body_text": body_text,
        "body_html": body_html,
        "received_at": received_at,
        "message_id": msg.get("Message-ID", ""),
        "in_reply_to": msg.get("In-Reply-To", ""),
        "references": msg.get("References", "")
    }

