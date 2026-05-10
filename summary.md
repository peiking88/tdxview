# 工作摘要

**时间:** 2026-05-10

## 变更概要

tdxview 项目初始提交

### 核心功能
- Streamlit Web 可视化平台，三层架构（UI → Services → Data）
- 数据源：通达信实时/历史行情、技术指标计算
- 缓存：MemoryCache (LRU+TTL) + DiskCache + CacheManager
- 存储：DuckDB 用户管理 + Parquet 时序数据
- 认证：JWT + bcrypt（已替换 passlib 兼容问题）
- 插件系统：自定义指标热重载

### 适配上游变更
- 适配 mootdx 0.16.0 / tdxdata 0.4.0 列名规范化
- conftest.py 支持未导入模块的 patch（importlib.import_module）

### 测试
- 单元 + 集成测试共 401 个用例，396 passed
- 双模式测试架构（mock/真实网络自动切换）
- Playwright E2E 测试（7 个页面对象）
