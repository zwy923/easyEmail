# EZmail - 智能邮件工作台

统一管理Gmail邮箱，自动分类、生成草稿回复、标记和提醒的智能邮件工作台。

## 功能特性

- **Gmail支持**: 支持Gmail邮箱的统一管理和同步
- **智能分类**: 使用OpenAI GPT模型自动分类邮件（紧急、重要、普通、垃圾、促销）
- **AI草稿生成**: 基于邮件上下文自动生成个性化回复草稿
- **RAG增强**: 使用检索增强生成（RAG）技术，基于历史邮件上下文生成更准确的回复
- **智能Agent**: AI智能体自动处理邮件
- **向量存储**: 使用pgvector存储邮件向量嵌入，支持语义搜索
- **定时任务**: 自动检查新邮件和分类处理
- **邮件同步**: 支持增量同步和删除同步
- **Web Dashboard**: 现代化的Web界面，可视化邮件与草稿管理

## 技术栈

### 后端
- **FastAPI**: 高性能Python Web框架
- **PostgreSQL + pgvector**: 关系型数据库，支持向量存储和相似度搜索
- **Redis**: 缓存和消息队列
- **Celery**: 异步任务队列
- **SQLAlchemy**: ORM框架
- **LangChain**: AI应用开发框架，支持RAG和Agent
- **OpenAI API**: GPT模型用于邮件分类、草稿生成和嵌入向量
- **Google Gmail API**: Gmail邮箱集成

### 前端
- **React**: UI框架
- **React Router**: 路由管理
- **Vite**: 构建工具
- **Axios**: HTTP客户端
- **date-fns**: 日期处理库

### 部署
- **Docker Compose**: 容器编排
- **Nginx**: 前端静态文件服务

## 项目结构

```text
easyEmail/
├── backend/                      # 后端代码
│   ├── main.py                  # FastAPI入口
│   ├── config.py                # 配置文件
│   ├── celery_worker.py         # Celery Worker配置
│   ├── api/                     # API路由
│   │   ├── routes_email/        # 邮件相关路由
│   │   │   ├── __init__.py      # 路由聚合
│   │   │   ├── auth.py          # OAuth认证
│   │   │   ├── accounts.py      # 邮箱账户管理
│   │   │   ├── emails.py        # 邮件操作
│   │   │   └── sync.py          # 邮件同步
│   │   └── routes_drafts.py     # 草稿管理路由
│   ├── services/                # 业务服务
│   │   ├── gmail_service.py     # Gmail API服务
│   │   ├── classification_service.py  # 邮件分类服务
│   │   ├── embedding_service.py      # 向量嵌入服务
│   │   ├── vector_store.py            # 向量存储服务
│   │   ├── rag_service.py             # RAG检索增强生成
│   │   ├── agent_service.py           # AI智能体服务
│   │   ├── agent_tools.py             # Agent工具集
│   │   ├── memory_service.py          # 记忆管理服务
│   │   └── scheduler.py               # 定时任务调度
│   ├── tasks/                   # Celery任务
│   │   └── email_tasks.py       # 邮件处理任务
│   ├── db/                      # 数据库
│   │   ├── models.py            # 数据模型
│   │   ├── schemas.py           # Pydantic模式
│   │   ├── crud.py              # CRUD操作
│   │   ├── database.py          # 数据库连接
│   │   └── migrations/          # 数据库迁移
│   └── utils/                   # 工具函数
│       ├── mail_parser.py       # 邮件解析
│       ├── oauth_utils.py       # OAuth工具
│       └── logging_config.py    # 日志配置
├── frontend/                    # 前端代码
│   ├── src/
│   │   ├── pages/              # 页面组件
│   │   │   ├── Dashboard.jsx   # 仪表板
│   │   │   ├── Inbox.jsx       # 收件箱
│   │   │   └── Drafts.jsx      # 草稿管理
│   │   ├── components/         # 通用组件
│   │   │   └── ConnectEmail.jsx
│   │   ├── api/                # API客户端
│   │   │   └── axiosInstance.js
│   │   └── App.jsx             # 应用入口
│   ├── package.json
│   └── vite.config.js
├── docker-compose.yml           # Docker编排（生产环境）
├── docker-compose.dev.yml       # Docker编排（开发环境）
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
cd easyEmail
```

### 2. 配置环境变量

在项目根目录创建`.env`文件，填入以下配置：

```bash
# 数据库配置
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/email_orchestrator

# Redis配置
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# OpenAI配置
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4
EMBEDDING_MODEL=text-embedding-3-small
VECTOR_DIMENSION=1536
RAG_TOP_K=5

# Gmail OAuth配置
GMAIL_CLIENT_ID=your-gmail-client-id
GMAIL_CLIENT_SECRET=your-gmail-client-secret
GMAIL_REDIRECT_URI=http://localhost:8000/api/email/gmail/callback

# 应用配置
SECRET_KEY=your-secret-key-change-in-production
FRONTEND_URL=http://localhost:5173
LOG_LEVEL=INFO
EMAIL_CHECK_INTERVAL=300
```

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

启动服务后，访问 http://localhost:8000/docs 查看完整的交互式API文档。

### 邮件相关 API

#### 认证和账户
- `GET /api/email/auth-url/{provider}`: 获取OAuth授权URL
- `GET /api/email/gmail/callback`: Gmail OAuth回调
- `POST /api/email/connect`: 连接邮箱账户
- `GET /api/email/accounts`: 获取已连接的邮箱账户列表
- `DELETE /api/email/accounts/{account_id}`: 删除邮箱账户

#### 邮件操作
- `GET /api/email/list`: 获取邮件列表（支持过滤和分页）
- `GET /api/email/{email_id}`: 获取邮件详情
- `POST /api/email/classify`: 手动触发邮件分类
- `POST /api/email/{email_id}/mark-read`: 标记为已读
- `POST /api/email/{email_id}/mark-important`: 标记为重要
- `DELETE /api/email/{email_id}`: 删除邮件

#### 邮件同步
- `POST /api/email/sync/{account_id}`: 手动触发邮件同步
- `GET /api/email/sync/status/{account_id}`: 获取同步状态

### 草稿相关 API

- `GET /api/drafts`: 获取草稿列表
- `GET /api/drafts/{draft_id}`: 获取草稿详情
- `POST /api/drafts`: 创建草稿
- `POST /api/drafts/generate`: 生成AI草稿
- `PUT /api/drafts/{draft_id}`: 更新草稿
- `DELETE /api/drafts/{draft_id}`: 删除草稿
- `POST /api/drafts/{draft_id}/send`: 发送草稿到Gmail

## 使用指南

### 1. 连接邮箱

1. 访问前端页面 http://localhost
2. 点击"连接邮箱"按钮
3. 选择Gmail提供商
4. 完成OAuth授权流程
5. 系统将自动开始同步邮件

### 2. 查看和管理邮件

1. 进入"收件箱"页面
2. 查看自动分类的邮件（紧急、重要、普通、垃圾、促销）
3. 使用过滤器按状态、分类、发件人等筛选邮件
4. 点击邮件查看详细信息
5. 可以手动触发分类或生成草稿

### 3. 生成和管理草稿

1. 在邮件详情页点击"生成草稿"
2. 选择回复语气（专业、友好、正式）
3. AI将基于邮件内容和历史上下文生成回复草稿
4. 在"草稿"页面查看和管理所有草稿
5. 编辑草稿后可直接发送到Gmail

### 4. 邮件同步

- 系统每5分钟自动检查新邮件
- 新邮件会自动触发分类任务
- 支持增量同步，只获取新邮件
- 支持删除同步，同步Gmail中的删除操作

## 开发指南

### 本地开发（不使用Docker）

#### 后端开发

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

#### 前端开发

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

系统配置了以下定时任务（通过Celery Beat调度）：

- **每5分钟**: 自动检查所有邮箱账户的新邮件
- **邮件处理**: 新邮件自动触发分类任务
- **向量嵌入**: 新邮件自动生成向量嵌入并存储到pgvector
- **邮件同步**: 定期同步已删除的邮件状态

可以通过修改 `backend/config.py` 中的 `EMAIL_CHECK_INTERVAL` 配置来调整检查间隔。

## 数据库迁移

首次运行时会自动创建数据库表。系统使用SQLAlchemy的`create_all`方法自动创建表结构。

### pgvector扩展

系统会自动启用pgvector扩展以支持向量存储。如果自动启用失败，可以手动执行：

```bash
# 进入数据库容器
docker-compose exec db psql -U postgres -d email_orchestrator

# 手动启用扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

### 数据库备份

建议定期备份PostgreSQL数据：

```bash
# 备份
docker-compose exec db pg_dump -U postgres email_orchestrator > backup.sql

# 恢复
docker-compose exec -T db psql -U postgres email_orchestrator < backup.sql
```

## 故障排除

### 数据库连接失败

检查PostgreSQL服务是否正常运行：
```bash
docker-compose ps db
docker-compose logs db
```

### Redis连接失败

检查Redis服务状态：
```bash
docker-compose ps redis
docker-compose logs redis
```

### Celery任务不执行

检查Celery Worker和Beat状态：
```bash
docker-compose logs celery_worker
docker-compose logs celery_beat
docker-compose ps celery_worker celery_beat
```

### OAuth授权失败

- 检查重定向URI是否与Google Cloud Console中配置的一致
- 确认`GMAIL_CLIENT_ID`和`GMAIL_CLIENT_SECRET`正确
- 检查OAuth应用是否已启用Gmail API
- 查看后端日志获取详细错误信息：`docker-compose logs backend`

### OpenAI API错误

- 确认`OPENAI_API_KEY`有效且有足够余额
- 检查API速率限制
- 查看日志了解具体错误：`docker-compose logs backend`

### 向量存储问题

- 确认pgvector扩展已正确安装和启用
- 检查向量维度配置是否与嵌入模型匹配
- 查看向量存储服务日志

### 查看日志

```bash
# 查看所有服务日志
docker-compose logs

# 查看特定服务日志
docker-compose logs backend
docker-compose logs celery_worker

# 实时跟踪日志
docker-compose logs -f backend
```

## 开发模式

项目提供了开发模式的Docker Compose配置：

```bash
# 使用开发配置启动
docker-compose -f docker-compose.dev.yml up -d
```

## 性能优化

- **向量搜索**: 使用pgvector的HNSW索引加速相似度搜索
- **缓存策略**: Redis缓存常用查询结果
- **异步处理**: Celery异步处理耗时任务（分类、生成草稿等）
- **批量操作**: 邮件同步使用批量API减少请求次数

## 安全注意事项

- 生产环境务必修改`SECRET_KEY`
- 使用HTTPS保护OAuth回调
- 定期更新依赖包以修复安全漏洞
- 限制API访问频率
- 妥善保管OAuth凭证和API密钥

## 许可证

MIT License
