# 工作摘要

**版本:** 1.1.0
**时间:** 2026-05-10

## v1.1.0 变更概要

重构数据管理模块，实现全类型数据导入/缓存/增量/重导闭环。

### 新增功能

- 全类型数据导入：支持 history/realtime/tick/financial/F10/basic 六种数据类型手工导入
- 导入状态跟踪：DuckDB data_imports 表记录每次导入的元信息
- 增量导入：history 类型基于上次 end_date 自动计算增量范围
- 手工重导：清除 Parquet + 记录后全量重新导入
- financial/F10/basic 缓存：补全了原缺失的缓存逻辑

### 改造内容

- ParquetManager：按 data_type 分区存储（data/parquet/{type}/...），旧路径 fallback 兼容
- DataService：新增 import_data/incremental_import/reimport_data 等通用导入方法
- 数据管理 UI：重写为 4 Tab 布局（数据导入/导入状态/数据浏览/数据源列表）
- E2E 测试：适配 Playwright 使用系统 Chromium，修复 strict mode 冲突，适配新 4 Tab 结构

### 测试

- 单元 + 集成测试：438 passed（TDX_LIVE=1），覆盖率 87.61%
- E2E 测试：46 passed，0 failed，0 skipped

---

## v1.0.0 初始版本

**时间:** 2026-05-10

### 核心功能

- Streamlit Web 可视化平台，三层架构（UI → Services → Data）
- 数据源：通达信实时/历史行情、技术指标计算
- 缓存：MemoryCache (LRU+TTL) + DiskCache + CacheManager
- 存储：DuckDB 用户管理 + Parquet 时序数据
- 认证：JWT + bcrypt
- 插件系统：自定义指标热重载
