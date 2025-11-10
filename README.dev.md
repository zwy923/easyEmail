# 开发环境使用说明

## 使用开发模式（npm run dev）

开发阶段推荐使用 `docker-compose.dev.yml`，它会：
- 使用 `npm run dev` 运行前端（支持热重载）
- 端口映射到 `5173`（Vite 默认端口）
- 自动挂载代码目录，修改代码后立即生效

## 启动开发环境

```bash
# 使用开发配置启动所有服务
docker-compose -f docker-compose.dev.yml up -d

# 查看日志
docker-compose -f docker-compose.dev.yml logs -f frontend

# 停止服务
docker-compose -f docker-compose.dev.yml down
```

## 访问地址

- 前端开发服务器: http://localhost:5173
- 后端API: http://localhost:8000
- 数据库: localhost:5432
- Redis: localhost:6379

## 生产环境

生产环境使用 `docker-compose.yml`，它会：
- 构建前端静态文件
- 使用 Nginx 提供服务
- 端口映射到 `80`

```bash
# 生产环境启动
docker-compose up -d
```

## 注意事项

1. **开发模式**：代码修改后会自动热重载，无需重启容器
2. **端口冲突**：确保 `5173` 端口未被占用
3. **环境变量**：开发模式中，前端通过 Vite 代理访问后端（`http://backend:8000`）
4. **node_modules**：使用匿名卷挂载，避免本地 node_modules 覆盖容器内的依赖

