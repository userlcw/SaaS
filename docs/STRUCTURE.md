# 目录结构说明

> 面向团队协作与后续扩展的 **项目组织约定**。所有新增文件请遵循本文件的分层规则，保持结构一致性。

## 1. 顶层布局

```
python/                          # 项目根（与仓库根一致）
├── backend/                     # 后端服务
├── frontend/                    # 前端资源
├── docs/                        # 项目文档
├── logs/                        # 运行日志（不入库，按天写入 YYYYMMDD.log）
├── scripts/                     # 部署 / 运维 / 数据脚本
├── pyproject.toml               # 项目元信息 + pytest / ruff / black 配置
├── README.md                    # 项目入口说明
└── .gitignore                   # Git 忽略规则
```

设计原则：

- **单一职责**：每个顶级目录只承担一类关注点。
- **就近扩展**：新增功能就近放到对应模块的子目录，不横跨。
- **配置外置**：所有可变项通过环境变量注入，禁止硬编码地址。
- **日志集中**：所有运行日志汇聚到根目录 `logs/`，方便排查。

## 2. 后端 `backend/`

```
backend/
├── app/                         # FastAPI 应用主体
│   ├── __init__.py
│   ├── main.py                  # 应用入口（创建 FastAPI 实例、中间件、异常处理、挂载）
│   ├── api/                     # 路由层（对外接口）
│   │   ├── __init__.py          # 导出 api_router
│   │   ├── router.py            # v1 汇总
│   │   └── v1/                  # v1 版本路由
│   │       ├── __init__.py
│   │       └── auth.py          # 认证相关 API：/login /me /logout
│   ├── core/                    # 框架级基础设施（不含业务）
│   │   ├── logger.py            # 日志：按天 + >20M gzip 压缩
│   │   ├── middleware.py        # 访问日志中间件（request_id / 耗时）
│   │   └── security.py          # 密码哈希 + JWT
│   ├── db/                      # 数据库连接与初始化
│   │   ├── session.py           # engine / SessionLocal / Base / get_db
│   │   └── init_db.py           # 建表 + 内置默认账号
│   ├── models/                  # SQLAlchemy ORM 模型
│   │   └── user.py
│   ├── schemas/                 # Pydantic 数据模型（请求/响应）
│   │   └── auth.py
│   ├── services/                # 业务逻辑层（被 api 调用）
│   │   └── auth_service.py
│   └── utils/                   # 通用工具函数（预留）
│
├── config/                      # 后端配置
│   ├── settings.py              # 全局 Settings（读 .env）
│   ├── .env.example             # 环境变量示例（提交到仓库）
│   └── .env                     # 本地实际环境变量（不提交）
│
├── data/                        # 运行时数据（SQLite / 缓存 / 上传等）
│   └── app.db                   # SQLite 主库（自动生成）
│
├── tests/                       # 后端单元测试
│   └── test_auth.py
│
└── requirements.txt             # 依赖清单
```

### 分层职责

| 层 | 职责 | 依赖方向 |
| --- | --- | --- |
| `api/` | HTTP 边界，参数校验、鉴权、组装响应 | 依赖 `services`、`schemas`、`db` |
| `services/` | 业务逻辑，事务、领域规则 | 依赖 `models`、`db`、`core` |
| `models/` | 持久化模型（表结构） | 依赖 `db` |
| `schemas/` | 传输层数据结构 | 无内部依赖 |
| `db/` | 数据库连接管理 | 依赖 `config` |
| `core/` | 框架基础设施 | 依赖 `config` |
| `config/` | 配置加载 | 顶层，无内部依赖 |

### 新增功能约定

新增一个业务模块（例如 `order`）应按以下方式落位：

```
backend/app/
├── api/v1/order.py          # 路由
├── services/order_service.py# 业务逻辑
├── models/order.py          # ORM
├── schemas/order.py         # 请求/响应
```

在 `backend/app/api/router.py` 中注册新路由；在 `backend/app/models/__init__.py` 中导入以确保元数据注册。

## 3. 前端 `frontend/`

```
frontend/
├── public/                      # 当前使用中的静态站点（同源挂载到 /static 与 /）
│   ├── index.html               # 登录页
│   ├── css/login.css
│   └── js/
│       ├── api.js               # 统一 API 封装（相对路径 /api/v1，不硬编码域名）
│       └── login.js             # 登录页逻辑
│
└── src/                         # 预留：未来接入 Vue/Vite/React 时使用
    ├── api/                     # 接口封装
    ├── assets/                  # 图片 / 字体
    ├── components/              # 通用组件
    ├── router/                  # 路由
    ├── stores/                  # 状态管理
    ├── utils/                   # 工具函数
    └── views/                   # 页面
```

**当前实现说明**：前端为最小可运行版本，位于 `public/` 下并由后端 `main.py` 同源挂载；根路径 `/` 返回 `index.html`，静态资源走 `/static/*`。如要引入构建型框架，请在 `frontend/` 独立初始化，构建产物输出到 `frontend/dist/` 并由后端挂载或反向代理转发。

**统一路由约束**：`api.js` 只使用相对路径 `/api/v1/*`，切勿写入 `http://localhost:8000` 之类的绝对地址，以便部署到任意域名时无需改动代码。

## 4. 文档 `docs/`

```
docs/
├── README.md         # 索引：先读哪个文档
├── handoff.md        # 项目状态、背景、待办、风险、已决策事项
├── AGENTS.md         # 协作规范、执行约束（提交前必读）
└── STRUCTURE.md      # 本文件：目录结构规范
```

## 5. 日志与运行时目录

- `logs/`：所有运行日志集中于此。
  - 命名：`YYYYMMDD.log`（如 `20260702.log`）。
  - 单文件 >20MB 自动压缩为 `YYYYMMDD_<n>.log.gz`，然后新建同名文件继续写入。
  - 跨天自动切换到新日期文件。
  - 不区分正常/错误级别，一个文件写入完整链路。

- `backend/data/`：SQLite 数据库、上传文件等运行时数据。**不入库**。

- `scripts/`：部署与运维脚本（例如数据库备份、日志清理）。命名建议 `verb-noun.ps1` 或 `verb-noun.sh`。

## 6. 配置文件管理

| 配置 | 位置 | 说明 |
| --- | --- | --- |
| 运行时环境变量 | `backend/config/.env` | 本地实际值，不入库 |
| 环境变量模板 | `backend/config/.env.example` | 入库；新同学复制为 `.env` 后使用 |
| Python 项目元信息 | `pyproject.toml` | pytest / ruff / black 均在此配置 |
| 依赖清单 | `backend/requirements.txt` | 生产依赖 |
| Git 忽略 | `.gitignore` | 顶层统一维护 |

## 7. 文件命名规范

- **Python**：模块 `lower_snake_case.py`；类 `PascalCase`；函数/变量 `lower_snake_case`。
- **测试**：文件 `test_*.py`；函数 `test_*`。
- **前端**：文件 `kebab-case.html/css/js`；组件（未来 Vue/React）`PascalCase.vue|tsx`。
- **文档**：`kebab-case.md` 或大写单词（如 `README.md`、`STRUCTURE.md`）。
- **脚本**：`verb-noun.<ext>`（如 `backup-db.ps1`、`clean-logs.ps1`）。

## 8. 使用注意事项

1. **禁止硬编码本地地址**：所有 URL 使用相对路径或环境变量注入。
2. **不提交 `.env`、`backend/data/*`、`logs/*`**：已在 `.gitignore` 中约束。
3. **新增依赖**：写入 `backend/requirements.txt`，本地清华源安装：
   `pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
4. **本地开发热加载**：`uvicorn backend.app.main:app --reload`；代码改动无需手动重启。
5. **数据库切换**：只需修改 `backend/config/.env` 中 `DATABASE_URL`，其他代码无需变更。
6. **单元测试**：`pytest` 会自动读取 `pyproject.toml` 中的配置，测试路径固定为 `backend/tests`。
7. **默认账号**：`admin_lcw / Xianyu12345@`，生产环境请首次登录后立即修改。

## 9. 依赖关系示意

```
main.py
  ├── core.middleware       (访问日志)
  ├── core.logger           (统一日志)
  ├── api.router            → api.v1.auth
  │                                └── services.auth_service
  │                                        ├── models.user
  │                                        ├── core.security
  │                                        └── db.session
  ├── db.init_db            → models.user
  └── config.settings       (被所有层依赖)
```

依赖方向严格从上到下，禁止下层反向依赖上层（如 `services` 不得依赖 `api`）。
