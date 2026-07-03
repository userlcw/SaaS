# Handoff — 项目交接与状态记录

> 本文档用于记录当前项目状态、背景、待办、风险以及已决策事项。每次交接或阶段性节点，请追加更新。

## 1. 项目背景

- 项目根目录：`c:\Users\WUKONG\Desktop\project\codex\python`
- 项目定位：前后端分离的登录系统脚手架
- 技术栈：FastAPI + SQLAlchemy + SQLite + bcrypt + JWT / 原生 HTML+CSS+JS

## 2. 当前状态

- 已完成：
  - 目录结构整理与规范化（详见 [STRUCTURE.md](./STRUCTURE.md)）
  - 后端登录系统：FastAPI + SQLAlchemy + SQLite + bcrypt + JWT
    - 接口：`POST /api/v1/auth/login`、`GET /api/v1/auth/me`、`POST /api/v1/auth/logout`、`GET /health`
    - 安全：bcrypt 密码哈希、JWT、参数化查询、CORS、基础安全响应头、登录失败限流锁定
    - 日志：按天写入 `logs/YYYYMMDD.log`，>20M 自动 gzip 压缩；含 request_id / 耗时 / 状态码 的访问日志
    - 默认管理员：`admin_lcw / Xianyu12345@`（首次启动自动创建，请尽快修改）
  - 前端登录页（`frontend/public/`）：深色渐变 + 白卡片 + 眼睛切换 + 记住我自动回填
  - 工程化：`.gitignore`、`pyproject.toml`（pytest/ruff/black）、根 `README.md`、`docs/STRUCTURE.md`
  - 数据文件归位：SQLite 落到 `backend/data/app.db`（相对 URL 自动归一化）
- 进行中：无
- 未开始：前端脚手架（Vue/Vite）、生产级数据库（MySQL/PostgreSQL）、刷新令牌

## 3. 目录结构说明

目录约定见 [docs/STRUCTURE.md](./STRUCTURE.md)。核心分层：

```
python/
├── backend/          # 后端 FastAPI 服务
│   ├── app/          # 应用主体（api/core/db/models/schemas/services/utils）
│   ├── config/       # 配置（settings.py / .env）
│   ├── data/         # 运行时数据（SQLite/缓存/上传）
│   ├── tests/        # 单元测试
│   └── requirements.txt
├── frontend/
│   ├── public/       # 当前使用（同源挂载）
│   └── src/          # 预留：未来接入 Vue/Vite
├── docs/             # 文档
├── logs/             # 运行日志
├── scripts/          # 部署 / 运维脚本
├── pyproject.toml    # 项目元信息 + pytest / ruff / black
├── README.md
└── .gitignore
```

## 4. 待办事项 (TODO)

- [ ] 修改默认管理员密码
- [ ] 引入前端构建型框架（Vue/Vite）时，产物输出到 `frontend/dist/` 并由后端挂载
- [ ] 切换到生产级数据库（配置 `DATABASE_URL`）
- [ ] 引入刷新令牌 / 单点登出黑名单

## 5. 风险与注意事项

- 严禁在网络请求中写死 `localhost` 或本地 IP，需统一走可配置的 baseURL。
- 严禁执行任何 `git` 命令，代码版本管理由用户手动完成。
- 严禁执行修改数据库数据的命令，除非用户明确要求。
- 使用外部资源时优先使用国内镜像源。

## 6. 已决策事项

- 前后端分离结构，后端 FastAPI；前端首版为原生 HTML/CSS/JS，与后端同源挂载。
- 日志集中写入项目根目录下 `logs/`，命名 `YYYYMMDD.log`，>20M 压缩滚动。
- SQLite 运行时数据统一落到 `backend/data/`，不放在项目根目录。
- 敏感与运行时文件（`.env`、`logs/*`、`backend/data/*`）不入库。

## 7. 变更历史

| 日期 | 内容 | 备注 |
| ---- | ---- | ---- |
| 2026-07-02 | 初始化目录结构与文档体系 | 建立 `docs/` 三件套 |
| 2026-07-02 | 完成后端登录系统与前端登录页 | 4 单测全通过 |
| 2026-07-02 | 补齐访问日志与全局异常上下文 | 日志含 request_id / 耗时 |
| 2026-07-02 | 目录结构整理 + `STRUCTURE.md` | SQLite 归位到 `backend/data/`；新增 `.gitignore`、`pyproject.toml`、根 `README.md` |
