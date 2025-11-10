"""日志相关API路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from backend.db.database import get_db
from backend.db import crud, models
from backend.db.schemas import LogResponse
from backend.utils.logging_config import log

router = APIRouter()


@router.get("", response_model=List[LogResponse])
async def get_logs(
    level: Optional[str] = Query(None, description="日志级别过滤"),
    module: Optional[str] = Query(None, description="模块过滤"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    db: Session = Depends(get_db)
):
    """获取日志列表"""
    logs, total = crud.get_logs(
        db,
        level=level,
        limit=limit,
        offset=offset
    )
    # 如果指定了module过滤，在结果中过滤
    if module:
        logs = [log_item for log_item in logs if log_item.module == module]
    return [LogResponse.model_validate(log_item) for log_item in logs]


@router.get("/{log_id}", response_model=LogResponse)
async def get_log(log_id: int, db: Session = Depends(get_db)):
    """获取日志详情"""
    log_item = db.query(models.Log).filter(models.Log.id == log_id).first()
    if not log_item:
        raise HTTPException(status_code=404, detail="日志不存在")
    return LogResponse.model_validate(log_item)

