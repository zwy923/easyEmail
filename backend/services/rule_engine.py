"""规则引擎：规则匹配和执行"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import re

from backend.utils.logging_config import log
from backend.db.models import Email, Rule, RuleAction, ClassificationCategory
from backend.db import crud
from backend.db.database import SessionLocal
from backend.services.classification_service import ClassificationService


class RuleEngine:
    """规则引擎类"""
    
    def __init__(self):
        self.classification_service = ClassificationService()
    
    def evaluate_rule(self, email: Email, rule: Rule) -> bool:
        """评估规则是否匹配邮件
        
        Returns:
            bool: 是否匹配
        """
        if not rule.is_active:
            return False
        
        conditions = rule.conditions
        if not conditions:
            return False
        
        # 检查发件人条件
        if "sender" in conditions:
            if not self._check_sender_condition(email, conditions["sender"]):
                return False
        
        # 检查主题条件
        if "subject" in conditions:
            if not self._check_subject_condition(email, conditions["subject"]):
                return False
        
        # 检查正文条件
        if "body" in conditions:
            if not self._check_body_condition(email, conditions["body"]):
                return False
        
        # 检查日期范围条件
        if "date_range" in conditions:
            if not self._check_date_range_condition(email, conditions["date_range"]):
                return False
        
        return True
    
    def _check_sender_condition(self, email: Email, condition: Dict) -> bool:
        """检查发件人条件"""
        if not condition:
            return True
        
        sender = email.sender_email or email.sender or ""
        sender_lower = sender.lower()
        
        # contains: 包含
        if "contains" in condition:
            return condition["contains"].lower() in sender_lower
        
        # equals: 完全匹配
        if "equals" in condition:
            return sender_lower == condition["equals"].lower()
        
        # starts_with: 开头匹配
        if "starts_with" in condition:
            return sender_lower.startswith(condition["starts_with"].lower())
        
        # ends_with: 结尾匹配
        if "ends_with" in condition:
            return sender_lower.endswith(condition["ends_with"].lower())
        
        # regex: 正则表达式
        if "regex" in condition:
            try:
                return bool(re.search(condition["regex"], sender, re.IGNORECASE))
            except re.error:
                return False
        
        return True
    
    def _check_subject_condition(self, email: Email, condition: Dict) -> bool:
        """检查主题条件"""
        if not condition:
            return True
        
        subject = email.subject or ""
        subject_lower = subject.lower()
        
        if "contains" in condition:
            return condition["contains"].lower() in subject_lower
        
        if "equals" in condition:
            return subject_lower == condition["equals"].lower()
        
        if "starts_with" in condition:
            return subject_lower.startswith(condition["starts_with"].lower())
        
        if "regex" in condition:
            try:
                return bool(re.search(condition["regex"], subject, re.IGNORECASE))
            except re.error:
                return False
        
        return True
    
    def _check_body_condition(self, email: Email, condition: Dict) -> bool:
        """检查正文条件"""
        if not condition:
            return True
        
        body = (email.body_text or email.body_html or "").lower()
        
        if "contains" in condition:
            return condition["contains"].lower() in body
        
        if "regex" in condition:
            try:
                return bool(re.search(condition["regex"], body, re.IGNORECASE))
            except re.error:
                return False
        
        return True
    
    def _check_date_range_condition(self, email: Email, condition: Dict) -> bool:
        """检查日期范围条件"""
        if not condition:
            return True
        
        received_at = email.received_at
        if not received_at:
            return False
        
        # after: 在某个日期之后
        if "after" in condition:
            try:
                after_date = datetime.fromisoformat(condition["after"].replace("Z", "+00:00"))
                if received_at.replace(tzinfo=None) < after_date:
                    return False
            except (ValueError, TypeError):
                pass
        
        # before: 在某个日期之前
        if "before" in condition:
            try:
                before_date = datetime.fromisoformat(condition["before"].replace("Z", "+00:00"))
                if received_at.replace(tzinfo=None) > before_date:
                    return False
            except (ValueError, TypeError):
                pass
        
        return True
    
    def execute_rule_actions(self, email: Email, rule: Rule, db) -> Dict:
        """执行规则动作
        
        Returns:
            Dict: 执行结果
        """
        actions = rule.actions
        if not actions:
            return {"success": False, "message": "规则无动作"}
        
        results = {}
        
        try:
            # 分类动作
            if actions.get("type") == RuleAction.CLASSIFY and actions.get("category"):
                category = ClassificationCategory(actions["category"])
                email.category = category
                email.classification_confidence = 90  # 规则匹配的置信度较高
                db.commit()
                results["classified"] = True
                log.info(f"规则 {rule.id} 对邮件 {email.id} 执行分类: {category.value}")
            
            # 标记重要
            if actions.get("mark_important", False):
                email.is_important = True
                db.commit()
                results["marked_important"] = True
                log.info(f"规则 {rule.id} 标记邮件 {email.id} 为重要")
            
            # 生成草稿（可选使用RAG上下文）
            if actions.get("generate_draft", False):
                # 如果启用RAG，使用带上下文的草稿生成
                use_rag = actions.get("use_rag_context", False)
                if use_rag:
                    try:
                        from backend.services.rag_service import RAGService
                        rag_service = RAGService()
                        draft_body = rag_service.generate_draft_with_context(
                            email,
                            tone=actions.get("tone", "professional")
                        )
                    except Exception as e:
                        log.warning(f"RAG草稿生成失败，回退到普通生成: {e}")
                        draft_body = self.classification_service.generate_draft(
                            email,
                            tone=actions.get("tone", "professional"),
                            length=actions.get("length", "medium")
                        )
                else:
                    draft_body = self.classification_service.generate_draft(
                        email,
                        tone=actions.get("tone", "professional"),
                        length=actions.get("length", "medium")
                    )
                if draft_body:
                    # 创建草稿记录
                    from backend.db.schemas import DraftCreate
                    draft = crud.create_draft(
                        db,
                        DraftCreate(
                            email_id=email.id,
                            subject=f"Re: {email.subject}" if email.subject else "回复",
                            body=draft_body
                        )
                    )
                    results["draft_created"] = True
                    results["draft_id"] = draft.id
                    log.info(f"规则 {rule.id} 为邮件 {email.id} 生成草稿: {draft.id}")
            
            # 转发
            if actions.get("type") == RuleAction.FORWARD and actions.get("forward_to"):
                # 这里应该调用邮箱服务发送转发邮件
                # 暂时只记录日志
                log.info(f"规则 {rule.id} 需要转发邮件 {email.id} 到 {actions['forward_to']}")
                results["forward_scheduled"] = True
            
            # 提醒
            if actions.get("type") == RuleAction.REMIND and actions.get("remind_after_hours"):
                # 这里应该创建提醒任务
                log.info(f"规则 {rule.id} 为邮件 {email.id} 创建提醒: {actions['remind_after_hours']}小时后")
                results["remind_scheduled"] = True
            
            # 更新规则匹配计数
            crud.increment_rule_match_count(db, rule.id)
            
            results["success"] = True
            return results
            
        except Exception as e:
            log.error(f"执行规则动作失败: {e}")
            return {"success": False, "message": str(e)}
    
    def process_email_with_rules(self, email: Email, db) -> List[Dict]:
        """处理邮件，应用所有匹配的规则
        
        Returns:
            List[Dict]: 执行的规则结果列表
        """
        # 获取所有活跃的规则，按优先级排序
        rules = crud.get_rules(db, is_active=True)
        
        results = []
        for rule in rules:
            if self.evaluate_rule(email, rule):
                result = self.execute_rule_actions(email, rule, db)
                result["rule_id"] = rule.id
                result["rule_name"] = rule.name
                results.append(result)
        
        return results

