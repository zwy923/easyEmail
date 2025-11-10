# 数据库迁移模块
# 由于文件名包含数字，使用importlib动态导入
import importlib.util
import os

def _load_enable_pgvector():
    """动态加载enable_pgvector_extension函数"""
    try:
        spec = importlib.util.spec_from_file_location(
            "enable_pgvector",
            os.path.join(os.path.dirname(__file__), "001_enable_pgvector.py")
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.enable_pgvector_extension
    except Exception:
        pass
    return None

enable_pgvector_extension = _load_enable_pgvector()

__all__ = ['enable_pgvector_extension'] if enable_pgvector_extension else []

