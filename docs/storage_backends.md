# tdxview 存储后端分析

## 概览

| 后端 | 实现位置 | tdxview 中状态 | 用途 |
|------|---------|---------------|------|
| DataFrame | 全链路传递 | **活跃** | 默认内存格式，不持久化 |
| CSV | tdxdata/storage/csv.py | **未使用** | `output="csv"` 从未被 tdxview 调用 |
| SQLite | tdxdata/storage/sqlite.py | **未使用** | `output="sqlite"` 从未被 tdxview 调用 |
| DuckDB | app/data/database.py | **活跃** | 用户、数据源、导入记录、日志 |
| Parquet | app/data/parquet_manager.py | **活跃** | K 线等时序数据持久化 |
| Parquet (tdxdata) | tdxdata/storage/parquet.py | **未使用** | `output="parquet"` 从未被 tdxview 调用 |
| Parquet (因子缓存) | tdxdata/sources/factor_cache.py | **活跃** | `~/.tdxdata/factors/` |
| DiskCache (JSON) | app/data/cache.py | **活跃** | `data/cache/` 查询结果缓存 |
| MemoryCache (LRU) | app/data/cache.py | **活跃** | 内存 LRU+TTL 缓存 |

---

## 1. DataFrame（内存传递）

**实现**：无独立存储类，`pd.DataFrame` 是全链路数据载体。

**数据流**：

```
tdxdata → TdxDataSource → DataService → VisualizationService → Plotly
```

**序列化点**：
- 缓存写入：`df.to_json(orient="columns", date_format="iso")` — `data_service.py:235`
- 缓存读取：`pd.DataFrame(cached)` — `data_service.py:222`

---

## 2. CSV

**实现**：`tdxdata/storage/csv.py` — `CSVStorage`

- `save()` → `df.to_csv(file_path, index=False, encoding="utf-8-sig")`
- `load()` → `pd.read_csv(file_path, encoding="utf-8-sig")`
- 路径：`{output_path}/{source}/{code}.csv`

**tdxview 使用情况**：零调用。`TdxDataSource` 从未传递 `output="csv"`。

**mootdx**：`mootdx/tools/tdx2csv.py` 有 `txt2csv()` 转换工具，但 tdxview 不使用。

---

## 3. SQLite

**实现**：`tdxdata/storage/sqlite.py` — `SQLiteStorage`

- `save()` → `df.to_sql(table_name, conn, if_exists="replace", index=False)`
- 数据库路径：`{output_path}/tdxdata.db`
- 表名：`{source}_{code}`

**tdxview 使用情况**：零调用。`TdxDataSource` 从未传递 `output="sqlite"`。

---

## 4. DuckDB

**实现**：`app/data/database.py` — `DatabaseManager`

**配置**：

| 配置项 | 位置 | 默认值 |
|--------|------|--------|
| `database.duckdb_path` | `app/config/settings.py:16` | `data/tdxview.db` |
| `database.wal_mode` | `app/config/settings.py:21` | `True` |
| `database.max_connections` | `app/config/settings.py:19` | `10` |

**Schema（11 张表）**，定义在 `scripts/init_database.py`：

| 表名 | 行号 | 用途 |
|------|------|------|
| `users` | 39-51 | 用户账号、角色、偏好 |
| `data_sources` | 57-70 | 数据源配置、优先级、健康状态 |
| `indicators` | 75-91 | 技术指标注册信息 |
| `dashboards` | 95-110 | 仪表盘布局、组件 |
| `charts` | 114-129 | 图表配置 |
| `time_index` | 133-145 | 时间索引与数据文件映射 |
| `asset_index` | 149-162 | 资产索引与数据文件路径 |
| `query_cache` | 166-179 | 查询缓存结果 |
| `system_logs` | 183-196 | 系统日志 |
| `audit_logs` | 200-213 | 审计日志 |
| `data_imports` | 217-231 | 数据导入记录、Parquet 路径 |

**API**：`execute / fetch_one / fetch_all / fetch_df / close`

**调用方**：

| 调用方 | 文件 | 访问表 |
|--------|------|--------|
| `DataService` | `app/services/data_service.py` | `data_sources`, `data_imports` |
| `UserService` | `app/services/user_service.py` | `users`, `dashboards` |
| `RetentionService` | `app/services/retention_service.py` | `system_logs`, `audit_logs` |
| `ConfigComponent` | `app/components/config.py` | 通过 DataService 间接访问 |
| `initialize_app()` | `app/main.py:150-170` | Schema 检查与初始化 |

---

## 5. Parquet

### 5.1 tdxview ParquetManager

**实现**：`app/data/parquet_manager.py` — `ParquetManager`

**路径规则**：

```
历史数据: {parquet_dir}/history/{year}/{month}/{symbol}.parquet
Tick数据:  {parquet_dir}/tick/{date}/{symbol}.parquet
其他:      {parquet_dir}/{data_type}/{symbol}.parquet
```

**配置**：`database.parquet_dir`，默认 `data/parquet`

**API**：`save / load / delete / list_symbols / list_data_types / get_parquet_info`

**调用方**：

| 方法 | 调用位置 |
|------|---------|
| `save()` | `DataService.fetch_and_store()` / `import_data()` / `parallel_fetch_and_store()` |
| `load()` | `DataService.load_from_parquet()` |
| `delete()` | `DataService.reimport_data()` |

### 5.2 tdxdata ParquetStorage

**实现**：`tdxdata/storage/parquet.py` — `ParquetStorage`

**tdxview 使用情况**：未使用。`TdxDataSource.fetch_to_parquet()` 定义了但从未被调用。

### 5.3 tdxdata FactorCache

**实现**：`tdxdata/sources/factor_cache.py` — `FactorCache`

- 路径：`~/.tdxdata/factors/{code}_{adjust}.parquet`
- 提供 `get / save / merge_and_save / last_date / clear`
- `merge_and_save()` 支持增量合并去重

**tdxview 使用情况**：活跃。通过 `tdxdata/sources/adjust.py:fetch_factor()` 间接调用。

---

## 6. 缓存层

### 6.1 MemoryCache

**实现**：`app/data/cache.py:35-102` — `MemoryCache`

- 基于 `OrderedDict` 的 LRU 缓存，支持每项 TTL
- 最大容量 128 项

### 6.2 DiskCache

**实现**：`app/data/cache.py:109-170` — `DiskCache`

- 存储为 `data/cache/{md5(key)}.cache` JSON 文件
- 格式：`{"expires_at": float, "value": any}`

### 6.3 CacheManager（两级缓存）

**实现**：`app/data/cache.py:177-219`

```
查询 → MemoryCache 命中? → 返回
     → DiskCache 命中? → 回填 MemoryCache → 返回
     → 未命中 → 获取数据 → 写入两级缓存
```

**调用方**：`DataService` / `IndicatorService`

---

## 数据流总图

```
[Streamlit UI]
      │
      ▼
[DataService] ←→ [CacheManager (Memory → Disk)]
      │
      ├──读──→ [ParquetManager] → data/parquet/history/YYYY/MM/code.parquet
      │
      ├──写──→ [ParquetManager.save()] + [DuckDB data_imports 记录]
      │
      ├──元数据──→ [DuckDB data_sources / users / dashboards]
      │
      └──获取──→ [TdxDataSource]
                     │
                     ├── fetch_hybrid() → 本地 TDX + 网络
                     │
                     └── fetch_factor() → tdxdata → FactorCache (~/.tdxdata/factors/)
```

---

## 死代码汇总

| 后端 | 位置 | 原因 |
|------|------|------|
| CSV | `tdxdata/storage/csv.py` | tdxview 从未传 `output="csv"` |
| SQLite | `tdxdata/storage/sqlite.py` | tdxview 从未传 `output="sqlite"` |
| Parquet (tdxdata) | `tdxdata/storage/parquet.py` | `TdxDataSource.fetch_to_parquet()` 定义但零调用 |
| Qlib | `tdxdata/storage/qlib.py` | 仅 tdxdata API 暴露，tdxview 不使用 |
