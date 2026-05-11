# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

tdxview 是基于 tdxdata（通达信数据接口）的股票数据可视化平台，通过 Streamlit Web 界面提供实时监控、历史数据分析、技术指标计算和交互式图表。中文项目，所有输出使用中文。

## 常用命令

```bash
# 一键环境搭建 + 启动（推荐）
bash scripts/setup_dev.sh all

# 环境搭建
bash scripts/setup_dev.sh setup

# 启动应用（默认端口 8501）
bash scripts/setup_dev.sh run
bash scripts/setup_dev.sh run --port 9000

# 运行单元 + 集成测试
bash scripts/setup_dev.sh test
bash scripts/setup_dev.sh test -- -k "test_data"

# 运行 E2E 测试（Playwright）
bash scripts/setup_dev.sh e2e

# 手动测试
source .venv/bin/activate
pytest tests/ --cov=app --cov-report=term-missing    # 全量测试 + 覆盖率
TDX_LIVE=0 pytest tests/ -q                           # 纯 mock 模式（离线）
TDX_LIVE=1 pytest tests/ -q                           # 强制真实网络
pytest tests/unit/test_data_service.py -v             # 单个测试文件
pytest tests/ -k "test_get_history" -v                # 单个测试函数

# 数据库初始化
python scripts/init_database.py                       # 默认管理员: admin / admin123

# 代码格式化
black app/ tests/ --line-length 100
isort app/ tests/ --profile black

# 类型检查
mypy app/
```

## 架构

三层架构：Streamlit UI → Services → Data Layer。

```
app/components/     Streamlit UI 页面（auth, charts, dashboard, indicators, config, data_management）
app/services/       业务逻辑层（data_service, visualization_service, indicator_service, user_service, backup_service, retention_service, plugin_service）
app/data/           数据层
  cache.py          MemoryCache (LRU+TTL) + DiskCache + CacheManager
  database.py       DuckDB 管理器（用户、数据源元数据）
  parquet_manager.py Parquet 时序数据读写
  models/           Pydantic 数据模型（user, data_source, indicator）
  sources/          DataSourceBase (ABC) → TdxDataSource（通达信适配器，封装 tdxdata 本地仓库 ~/peiking88/tdxdata）
app/config/         Pydantic Settings 配置管理，从 config.yaml + .env 加载
app/utils/          工具模块
  indicators/       内置指标实现（trend: SMA/EMA/MACD, momentum: RSI/RPS, volatility: Bollinger, volume: OBV/VWAP, custom: 动态加载器）
  logging.py        Loguru 日志配置
```

**关键数据流**：DataService 协调 CacheManager → DuckDB → ParquetManager → TdxDataSource 的查询链路，支持并行多股票获取。

## 配置

- `config.yaml`：主配置文件（数据库路径、缓存、TDX 数据源、安全、日志等）
- `app/config/settings.py`：Pydantic Settings 模型，`get_settings()` 全局单例
- 环境变量覆盖：`APP_SECRET_KEY`, `TDXDATA_API_KEY`, `CONFIG_FILE`, `ENVIRONMENT`, `TDX_LIVE`

## 测试体系

**双模式测试架构**（`tests/conftest.py`）：

- `test_settings`（session, autouse）：创建指向临时目录的真实 Settings，自动 patch 所有 18 个应用模块的 `get_settings`
- `tdx_source`（session）：自动检测通达信服务器 → 可用返回真实 TdxDataSource，不可用返回 MagicMock（预设 A 股数据）
- 环境控制：`TDX_LIVE=0`（强制 mock）、`TDX_LIVE=1`（强制真实）、默认自动检测

**测试分类**：

- `tests/unit/`：单元测试（services, data layer, indicators）
- `tests/integration/`：集成测试（数据流、API、端到端）
- `tests/e2e/`：Playwright 浏览器测试（Page Object Model，7 个页面对象）

**覆盖率配置**（`pyproject.toml`）：排除 `app/components/*`、`tdxdata_source.py`、`main.py`，下限 80%。

## 插件系统

- 自定义指标脚本放在 `plugins/indicators/`，需实现 `calculate(df, **params) -> pd.DataFrame` 函数
- `PluginService` 通过文件哈希变更检测实现热重载，无需重启应用

## 约束

- **tdxdata 依赖**：通过本地仓库 `~/peiking88/tdxdata` 以 editable 模式安装，禁止修改 tdxdata 源码
- 数据源适配器 `TdxDataSource` 封装 tdxdata 库，所有访问通过 `DataSourceBase` 抽象接口
- 所有 Pydantic 模型定义在 `app/data/models/`
- 数值格式：价位金额 `%.2f`、数量 `%d`、百分比 `%d%%`
