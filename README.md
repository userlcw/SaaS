# Login System

一个基于 **FastAPI + SQLAlchemy + bcrypt + JWT** 的前后端分离登录系统脚手架。前端为原生 HTML/CSS/JS，静态资源同源挂载在后端，避免部署时跨源与硬编码地址。

## 目录速览

```
python/
├── backend/          # 后端 (FastAPI)
├── frontend/         # 前端 (静态资源)
├── docs/             # 文档
├── logs/             # 运行日志（按天写入，>20M 压缩）
├── scripts/          # 部署 / 运维脚本
├── pyproject.toml    # 项目元信息 + pytest / ruff / black 配置
└── .gitignore
```

详细结构与规范请阅读 [docs/STRUCTURE.md](docs/STRUCTURE.md)。

## 快速开始

```powershell
# 1. 创建虚拟环境并安装依赖（国内清华镜像）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 复制环境变量
Copy-Item backend\config\.env.example backend\config\.env

# 3. 启动（本地热加载）
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

访问：

- 登录页：http://127.0.0.1:8000/
- Swagger：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

## 默认账号

- 用户名：`admin_lcw`
- 密码：`Xianyu12345@`

## 运行测试

```powershell
pytest -q
```

## 相关文档

- [docs/README.md](docs/README.md) — 文档索引
- [docs/handoff.md](docs/handoff.md) — 项目状态与交接
- [docs/AGENTS.md](docs/AGENTS.md) — 协作规范
- [docs/STRUCTURE.md](docs/STRUCTURE.md) — 目录结构说明
