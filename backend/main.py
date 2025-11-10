"""FastAPI应用入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from backend.config import settings
from backend.utils.logging_config import log
from backend.db.models import Base
from backend.db.database import engine, SessionLocal
from backend.api import routes_email, routes_rules


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时创建数据库表
    log.info("创建数据库表...")
    Base.metadata.create_all(bind=engine)
    log.info("数据库表创建完成")
    
    # 启用pgvector扩展
    try:
        from backend.db.migrations import enable_pgvector_extension
        if enable_pgvector_extension:
            enable_pgvector_extension()
    except Exception as e:
        log.warning(f"启用pgvector扩展失败: {e}")
    
    yield
    
    # 关闭时清理
    log.info("应用关闭")


# 创建FastAPI应用
app = FastAPI(
    title="AI邮件编排系统",
    description="统一管理多个邮箱，自动分类、生成草稿回复",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
app.include_router(routes_email.router, prefix="/api/email", tags=["邮件"])
app.include_router(routes_rules.router, prefix="/api/rules", tags=["规则"])


@app.get("/")
async def root():
    """根路径"""
    return {"message": "AI邮件编排系统 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    log.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )

