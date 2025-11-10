"""规则相关API路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from backend.db.database import get_db
from backend.db import crud
from backend.db.schemas import RuleCreate, RuleUpdate, RuleResponse
from backend.utils.logging_config import log

router = APIRouter()


@router.get("", response_model=List[RuleResponse])
async def get_rules(
    is_active: bool = None,
    db: Session = Depends(get_db)
):
    """获取规则列表"""
    rules = crud.get_rules(db, is_active=is_active)
    return [RuleResponse.model_validate(rule) for rule in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(rule_id: int, db: Session = Depends(get_db)):
    """获取规则详情"""
    rule = crud.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return RuleResponse.model_validate(rule)


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    rule: RuleCreate,
    db: Session = Depends(get_db)
):
    """创建规则"""
    try:
        db_rule = crud.create_rule(db, rule)
        log.info(f"创建规则: {db_rule.id} - {db_rule.name}")
        return RuleResponse.from_orm(db_rule)
    except Exception as e:
        log.error(f"创建规则失败: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    rule_update: RuleUpdate,
    db: Session = Depends(get_db)
):
    """更新规则"""
    rule = crud.update_rule(db, rule_id, rule_update)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    log.info(f"更新规则: {rule_id}")
    return RuleResponse.model_validate(rule)


@router.delete("/{rule_id}")
async def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    """删除规则"""
    success = crud.delete_rule(db, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    log.info(f"删除规则: {rule_id}")
    return {"success": True}


@router.post("/{rule_id}/toggle")
async def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    """启用/禁用规则"""
    rule = crud.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    
    rule.is_active = not rule.is_active
    db.commit()
    db.refresh(rule)
    
    log.info(f"{'启用' if rule.is_active else '禁用'}规则: {rule_id}")
    return {"success": True, "is_active": rule.is_active}

