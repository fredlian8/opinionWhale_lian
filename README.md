# Opinion Whale Tracker

面向预测市场的“巨鲸监控”与市场可视化项目，包含 Python FastAPI 后端与简单前端页面。后端聚合 Opinion CLOB API 的市场与订单簿数据，提炼买卖墙与大额委托，前端展示基础信息。

## 技术栈

- 后端：`FastAPI` + `pydantic`，结构清晰、性能优良
- SDK：`opinion_clob_sdk`（封装对 Opinion 代理网关的访问）
- 运行环境：Python 3.10+
- 前端：静态页面（`frontend/` 与 `public/`），通过浏览器访问后端 API

## 目录结构

- `backend/`：后端服务入口与业务逻辑（`main.py`）
- `api/`：无框架的简易 HTTP 处理器示例（`markets.py`）
- `frontend/`、`public/`：静态资源与示例页面
- `requirements.txt`：后端依赖清单（位于 `backend/`）

## 环境变量

- `OPINION_API_KEY`：后端访问 Opinion 代理网关所需的 API Key（必填）

为保证安全，代码中不再包含任何密钥或令牌。请在本地或部署环境以环境变量方式注入，不要将 `.env*` 文件提交到仓库。

## 安装与运行

1. 创建虚拟环境并安装依赖：
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```
2. 设置环境变量：
   ```bash
   export OPINION_API_KEY="<your-key>"
   ```
3. 启动后端：
   ```bash
   python backend/main.py
   # 或使用 uvicorn：
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

服务启动后，访问：

- `GET /`：健康检查
- `GET /api/markets`：聚合市场与巨鲸信息
- `GET /api/markets/{market_id}`：单市场详情
- `GET /api/whales?threshold=500`：按阈值过滤的大额委托/买卖墙
- `GET /api/orderbook/{token_id}`：订单簿（bids/asks）
- `GET /api/stats`：总览统计

示例请求：

```bash
curl http://localhost:8000/api/markets
curl "http://localhost:8000/api/whales?threshold=1000"
```

## 关键实现

- 市场聚合：分页拉取并合并市场列表，兼容二元与分类市场结构
- 价格/订单簿：对 `yes_token_id` 拉取当前价格与订单簿，计算买卖墙价值
- 巨鲸检测：基于可配置阈值（默认 500 USD）识别买卖侧的大额挂单
- 缓存与刷新：定时刷新缓存，避免频繁调用上游 API

后端核心入口：`backend/main.py`。

## 安全与合规

- 绝不在仓库中保存密钥、令牌或私人配置
- `.gitignore` 已忽略常见敏感与本地文件（`venv/`、`.env*`、`__pycache__/` 等）
- 若未设置 `OPINION_API_KEY`，后端将返回空数据而非抛出敏感信息

## 部署建议

- 将 `OPINION_API_KEY` 作为托管平台的环境变量注入（如 Vercel/Render/Railway 等）
- 使用反向代理或边缘缓存降低上游 API 压力和时延
- 配置健康检查与日志收集，监控刷新任务与调用错误率

## 开发提示

- 添加更多数据源：可在 `process_market` 与 `detect_whales` 中扩展策略
- 指标与告警：接入 Prometheus/Grafana，针对买卖墙变动做告警
- 前端可视化：将 `whales` 列表与 `orderbook` 转为图形展示，提高可读性

## 许可

本项目用于技术演示与学习目的，请在遵守上游 API 使用条款的前提下进行二次开发。

