"""启用pgvector扩展的迁移脚本"""
from sqlalchemy import text
from backend.db.database import engine
from backend.utils.logging_config import log

def enable_pgvector_extension():
    """启用pgvector扩展"""
    try:
        with engine.begin() as conn:  # 使用begin()自动提交
            # 启用pgvector扩展
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            log.info("pgvector扩展已启用")
            
            # 创建向量索引（如果email_embeddings表已存在）
            # 注意：PGVector会自动管理索引，这里只是备用
            try:
                # 检查表是否存在
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'langchain_pg_embedding'
                    )
                """))
                table_exists = result.scalar()
                
                if table_exists:
                    log.info("PGVector表已存在")
                else:
                    log.info("PGVector表将在首次使用时创建")
            except Exception as e:
                log.warning(f"检查PGVector表失败: {e}")
                
    except Exception as e:
        log.error(f"启用pgvector扩展失败: {e}", exc_info=True)
        # 不抛出异常，允许应用继续运行（扩展可能已经存在）


if __name__ == "__main__":
    enable_pgvector_extension()

