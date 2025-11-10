FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 升级pip
RUN pip install --upgrade pip setuptools wheel

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖（使用--no-deps避免自动安装冲突的依赖，然后单独安装）
RUN pip install --no-cache-dir -r requirements.txt || \
    (pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt)

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p logs

# 设置PYTHONPATH，确保可以导入backend模块
ENV PYTHONPATH=/app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

