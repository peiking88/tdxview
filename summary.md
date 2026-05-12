# 工作摘要

**版本:** 1.3.0
**时间:** 2026-05-12

## v1.3.0 去掉缓存层，改用 DuckDB 作为唯一本地存储

移除 MemoryCache/DiskCache/CacheManager 两层缓存架构，所有数据查询直接走 DuckDBStore，未命中时从远程获取后存入。

### 核心改动

- 删除 `app/data/cache.py`（219 行），移除 MemoryCache、DiskCache、CacheManager、generate_cache_key
- DuckDBStore 所有 `_save_*` 方法从 `DELETE+INSERT` 改为 `INSERT OR REPLACE`，避免部分写入覆盖完整数据
- DataService 重写：查询模式为先查 DuckDBStore → 有则返回 → 无则远程获取 → 存入
- IndicatorService 移除缓存，指标每次重新计算
- RetentionService 移除磁盘缓存清理逻辑

### 配置精简

- 删除 `CacheConfig` 类及 `cache_dir`、`cache_enabled`、`cache_ttl` 等字段
- config.yaml 删除 `cache:` 段

### UI 更新

- "缓存配置"改为"存储管理"，展示 DuckDB 各表数据量和数据库优化按钮

### 测试

- 单元测试：337 passed
- 集成测试：74 passed
- 覆盖率：85.97%
- 真实网络测试：全部通过

---

## v1.2.0 移除 external/ 依赖，优化 UI 分页与导航

**时间:** 2026-05-11

---

## v1.1.0 全类型数据导入/缓存/增量/重导闭环

**时间:** 2026-05-10

---

## v1.0.0 初始版本

**时间:** 2026-05-10
