# 本地运行手册

## 路径约定

所有命令均从项目根目录执行。不要把 `.runtime`、`data/postgres`、`data/raw` 或 `models` 移出项目目录。

## 数据库

```powershell
.\.runtime\conda\python.exe scripts\postgres_runtime.py start
.\.runtime\conda\python.exe scripts\postgres_runtime.py status
.\.runtime\conda\python.exe scripts\postgres_runtime.py stop
```

端口：`55432`。数据库、用户、开发密码均为 `olistops`；该配置仅绑定 `127.0.0.1`，公开部署前必须更换。

重新导入数据：

```powershell
.\.runtime\conda\python.exe scripts\download_olist.py
.\.runtime\conda\python.exe scripts\load_data.py
.\.runtime\conda\python.exe scripts\data_quality_report.py
.\.runtime\conda\python.exe scripts\build_knowledge.py
```

## Ollama

```powershell
$env:OLLAMA_MODELS = (Resolve-Path .\models\ollama)
.\.runtime\ollama\ollama.exe serve
```

另开 PowerShell：

```powershell
$env:OLLAMA_MODELS = (Resolve-Path .\models\ollama)
.\.runtime\ollama\ollama.exe pull qwen2.5:3b
.\.runtime\ollama\ollama.exe ps
```

## API 与 Web

前台调试：

```powershell
$env:PYTHONNOUSERSITE = '1'
.\.runtime\conda\python.exe -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000 --reload
npm --prefix apps/web run dev
```

后台启动：

```powershell
.\scripts\start.ps1
```

日志保存在 `.runtime/logs`。

## 故障排查

- API `degraded` 且数据库为空：运行 `postgres_runtime.py start`。
- `vector_enabled=false`：重新运行 `scripts/load_data.py`，确认 Conda 环境含 pgvector。
- 模型 `unavailable`：检查 11434 端口和 `.runtime/logs/ollama.err.log`。
- 模型不存在：执行 `ollama.exe pull qwen2.5:3b`；模板回退不受影响。
- 前端按钮不可用：先检查 `http://127.0.0.1:8000/healthz`。
- 数据导入失败：修复后可安全重跑；RAW 表会在 COPY 前清空，MART 会事务式重建。
