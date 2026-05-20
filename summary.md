# 工作摘要

**时间:** 2026-05-20 12:35:00

## 变更概要
- 修复分钟级 K 线（1m/5m）数据列不一致问题：清除 mootdx 生成的冗余列（year/month/day/hour/minute/datetime），统一为 stock_code/date/open/high/low/close/volume/amount
- 修复 1m/5m 最后一笔 bar 时间标签差异：TDX 标记区间起始时刻，现偏移到结束时刻，与 15m/30m/1h（pandas resample）保持一致
- 修复 _clean_single 误删最后一笔不完整 bar：成交量/价格异常过滤跳过最后一行
- 修复分钟图 rangebreak 遮盖 11:30/15:00 收盘 bar：午休起始于 11:30:01，盘后起始于 15:00:01
- 过滤 TDX 服务器预生成的未来 bar（午休期间返回的 13:00 占位 bar）
- 分钟级 end_date 扩展到 23:59:59，避免 tdxdata 午夜截断

## 最近提交
```
7abfcae chore: 升级 tdxdata 依赖版本至 ≥1.0.0，同步升级关联包
2bafd8a feat: 彻底移除 DuckDB 依赖，精简架构
2a94b9a docs: 更新 README.md 变更日志和 summary.md
bfccee6 feat: 分钟K线图表支持，简化数据层，升级 tdxdata>=0.8.0
66cc214 v1.5.2
```
