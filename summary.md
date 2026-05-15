# 工作摘要

**时间:** 2026-05-15

## 变更概要
增强图表可视化：分钟级K线支持（非交易时段隐藏、自动轴格式）、图表自适应宽度。简化数据层：移除历史数据缓存、统一走 hybrid 获取、升级 tdxdata>=0.8.0。新增后台服务管理（start/stop/status/restart/logs）。

## 变更文件
- `app/services/visualization_service.py` — 分钟K线支持：非交易时段 rangebreak、%H:%M 轴格式、动态宽度（5px/根）、密集模式（>100根隐藏滑块）
- `app/data/sources/tdxdata_source.py` — 所有周期统一走 fetch_hybrid（tdxdata>=0.8.0 内置重采样）
- `app/services/data_service.py` — get_history 移除 DuckDB 缓存层，直接调 tdxdata 接口
- `app/components/indicators.py` — 新增 K 线周期选择器，图表自适应宽度
- `app/components/charts.py` — 移除均线/布林叠加控件和导出按钮，简化 UI
- `app/main.py` — 移除系统管理页面
- `scripts/setup_dev.sh` — 新增 start/stop/status/restart/logs 后台管理命令
- `tests/e2e/` — 移除 config_page 测试
- `tests/unit/test_data_layer.py` — 更新 data_service 测试
- `pyproject.toml` — tdxdata>=0.8.0，版本升级至 1.6.0
