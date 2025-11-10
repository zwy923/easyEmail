# EZmail重新设计现代和美观的排版

统一管理Gmail邮箱，自动分类、生成草稿回复、标记和提醒的智能邮件工作台。

## 功能特性

- **Gmail支持**: 支持Gmail邮箱的统一管理
- **智能分类**: 使用OpenAI GPT模型自动分类邮件（紧急、重要、普通、垃圾、促销）
- **草稿生成**: AI自动生成邮件回复草稿
- **定时任务**: 自动检查新邮件和分类处理
- **Web Dashboard**: 现代化的Web界面，可视化邮件与草稿管理

## 技术栈

### 后端
- **FastAPI**: 高性能Python Web框架
- **PostgreSQL**: 关系型数据库
- **Redis**: 缓存和消息队列
- **Celery**: 异步任务队列
- **SQLAlchemy**: ORM框架
- **OpenAI API**: 邮件分类和草稿生成

### 前端
- **React**: UI框架
- **Vite**: 构建工具
- **Axios**: HTTP客户端

### 部署
- **Docker Compose**: 容器编排

## 项目结构

```
ai_email_orchestrator/
├── backend/                 # 后端代码
│   ├── main.py             # FastAPI入口
│   ├── config.py           # 配置文件
│   ├── api/                # API路由
│   │   └── routes_email.py
│   ├── services/           # 业务服务
│   │   ├── gmail_service.py
│   │   ├── classification_service.py
│   │   └── scheduler.py
│   ├── tasks/             # Celery任务
│   │   └── email_tasks.py
│   ├── db/                # 数据库
│   │   ├── models.py
│   │   ├── schemas.py
│   │   └── crud.py
│   └── utils/             # 工具函数
│       ├── mail_parser.py
│       └── oauth_utils.py
├── frontend/              # 前端代码
│   ├── src/
│   │   ├── pages/        # 页面组件
│   │   ├── api/          # API客户端
│   │   └── App.jsx
│   └── package.json
├── docker-compose.yml     # Docker编排
└── README.md
```

## 快速开始

### 前置要求

- Docker和Docker Compose
- OpenAI API密钥
- Gmail OAuth应用凭证

### 1. 克隆项目

```bash
git clone <repository-url>
cd ai_email_orchestrator
```

### 2. 配置环境变量

复制`.env.example`为`.env`并填写配置：

```bash
cp .env.example .env
```

编辑`.env`文件，填入以下信息：

- `OPENAI_API_KEY`: OpenAI API密钥
- `GMAIL_CLIENT_ID`和`GMAIL_CLIENT_SECRET`: Gmail OAuth凭证

### 3. 启动服务

```bash
docker-compose up -d
```

这将启动以下服务：
- PostgreSQL数据库（端口5432）
- Redis（端口6379）
- FastAPI后端（端口8000）
- Celery Worker
- Celery Beat（定时任务）
- 前端（端口80）

### 4. 访问应用

- 前端: http://localhost
- API文档: http://localhost:8000/docs

## OAuth配置

### Gmail OAuth设置

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 启用Gmail API
4. 创建OAuth 2.0客户端ID
5. 添加授权重定向URI: `http://localhost:8000/api/email/gmail/callback`
6. 复制客户端ID和密钥到`.env`文件

## API文档

### 邮件相关

- `GET /api/email/auth-url/{provider}`: 获取OAuth授权URL
- `POST /api/email/connect`: 连接邮箱账户
- `GET /api/email/list`: 获取邮件列表
- `GET /api/email/{email_id}`: 获取邮件详情
- `POST /api/email/classify`: 手动触发分类
- `POST /api/email/draft`: 生成草稿
- `POST /api/email/{email_id}/mark-read`: 标记为已读
- `POST /api/email/{email_id}/mark-important`: 标记为重要

## 使用指南

### 1. 连接邮箱

1. 访问前端页面
2. 点击"连接邮箱"
3. 选择Gmail
4. 完成OAuth授权
5. 系统将自动开始获取邮件

### 2. 查看邮件

1. 进入"收件箱"页面
2. 查看自动分类的邮件
3. 可以手动触发分类或生成草稿
4. 点击邮件查看详情

## 开发

### 本地开发（不使用Docker）

#### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

#### 前端

```bash
cd frontend
npm install
npm run dev
```

#### Celery Worker

```bash
cd backend
celery -A backend.celery_worker worker --loglevel=info
```

#### Celery Beat

```bash
cd backend
celery -A backend.celery_worker beat --loglevel=info
```

## 定时任务

系统配置了以下定时任务：

- **每5分钟**: 自动检查所有邮箱账户的新邮件
- **邮件处理**: 新邮件自动触发分类任务

## 数据库迁移

首次运行会自动创建数据库表。如需手动迁移：

```bash
# 进入后端容器
docker-compose exec backend bash

# 使用Alembic（如果配置了）
alembic upgrade head
```

## 故障排除

### 数据库连接失败

检查PostgreSQL服务是否正常运行：
```bash
docker-compose ps db
```

### Celery任务不执行

检查Redis连接和Celery Worker状态：
```bash
docker-compose logs celery_worker
```

### OAuth授权失败

- 检查重定向URI是否与配置一致
- 确认OAuth凭证正确
- 查看后端日志获取详细错误信息

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

如有问题，请提交Issue或联系维护者。

