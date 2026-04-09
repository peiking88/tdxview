#!/usr/bin/env python3
"""
数据库初始化脚本
用于创建tdxview系统所需的数据库表结构和索引
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import get_settings

def init_database():
    """初始化数据库"""
    settings = get_settings()
    db_path = settings.database.duckdb_path
    
    print(f"初始化数据库: {db_path}")
    
    # 确保数据目录存在
    data_dir = Path(settings.database.parquet_dir)
    cache_dir = Path(settings.database.cache_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    import duckdb
    
    # 连接数据库
    conn = duckdb.connect(db_path)
    
    # 创建用户表
    print("创建用户表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP,
        preferences JSON,
        is_active BOOLEAN DEFAULT TRUE,
        role TEXT DEFAULT 'user'  -- 'user', 'admin'
    )
    """)
    
    # 创建数据源配置表
    print("创建数据源配置表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS data_sources (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,  -- 'tdxdata', 'csv', 'api', 'file'
        config JSON NOT NULL,
        priority INTEGER DEFAULT 1,
        enabled BOOLEAN DEFAULT TRUE,
        last_checked TIMESTAMP,
        error_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建指标定义表
    print("创建指标定义表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS indicators (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        display_name TEXT NOT NULL,
        category TEXT NOT NULL,  -- 'trend', 'momentum', 'volatility', 'volume', 'custom'
        description TEXT,
        parameters JSON,  -- 默认参数
        script_path TEXT,  -- 自定义指标脚本路径
        is_builtin BOOLEAN DEFAULT TRUE,
        is_enabled BOOLEAN DEFAULT TRUE,
        version TEXT DEFAULT '1.0',
        author TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建仪表板配置表
    print("创建仪表板配置表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS dashboards (
        id INTEGER PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        name TEXT NOT NULL,
        description TEXT,
        layout JSON NOT NULL,  -- 布局配置
        widgets JSON NOT NULL,  -- 小部件配置
        tags JSON,  -- 标签
        is_public BOOLEAN DEFAULT FALSE,
        is_default BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建图表配置表
    print("创建图表配置表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS charts (
        id INTEGER PRIMARY KEY,
        dashboard_id INTEGER REFERENCES dashboards(id),
        name TEXT NOT NULL,
        chart_type TEXT NOT NULL,  -- 'candlestick', 'line', 'bar', 'heatmap', 'scatter'
        data_config JSON NOT NULL,  -- 数据配置
        style_config JSON NOT NULL,  -- 样式配置
        layout_config JSON NOT NULL,  -- 布局配置
        indicators JSON,  -- 关联的指标
        position JSON,  -- 在仪表板中的位置
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建时间索引表
    print("创建时间索引表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS time_index (
        date DATE PRIMARY KEY,
        data_file_path TEXT NOT NULL,  -- Parquet文件路径
        record_count INTEGER,
        symbol_count INTEGER,
        min_timestamp TIMESTAMP,
        max_timestamp TIMESTAMP,
        file_size_bytes INTEGER,
        compression_ratio FLOAT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建资产索引表
    print("创建资产索引表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS asset_index (
        symbol TEXT PRIMARY KEY,
        name TEXT,
        market TEXT,  -- 'SZ', 'SH', 'HK', etc.
        data_file_paths JSON NOT NULL,  -- 相关数据文件路径
        first_date DATE,
        last_date DATE,
        record_count INTEGER,
        data_points INTEGER,  -- 总数据点数
        last_updated TIMESTAMP,
        is_active BOOLEAN DEFAULT TRUE
    )
    """)
    
    # 创建查询缓存表
    print("创建查询缓存表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS query_cache (
        cache_key TEXT PRIMARY KEY,
        query_type TEXT NOT NULL,  -- 'data', 'indicator', 'aggregate'
        query_params JSON NOT NULL,
        result_data JSON NOT NULL,
        result_metadata JSON NOT NULL,
        result_size_bytes INTEGER,
        hit_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建系统日志表
    print("创建系统日志表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY,
        level TEXT NOT NULL,  -- 'INFO', 'WARNING', 'ERROR', 'DEBUG'
        module TEXT NOT NULL,
        message TEXT NOT NULL,
        details JSON,
        user_id INTEGER,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建审计日志表
    print("创建审计日志表...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        action TEXT NOT NULL,  -- 'login', 'logout', 'query', 'update', 'delete'
        resource_type TEXT NOT NULL,  -- 'dashboard', 'chart', 'indicator', 'data'
        resource_id TEXT,
        details JSON,
        ip_address TEXT,
        user_agent TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建索引
    print("创建索引...")
    
    # 用户表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)")
    
    # 数据源表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_sources_type ON data_sources(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_data_sources_enabled ON data_sources(enabled)")
    
    # 指标表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_indicators_category ON indicators(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_indicators_is_builtin ON indicators(is_builtin)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_indicators_name ON indicators(name)")
    
    # 仪表板表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dashboards_user_id ON dashboards(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dashboards_is_public ON dashboards(is_public)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dashboards_created_at ON dashboards(created_at)")
    
    # 图表表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_charts_dashboard_id ON charts(dashboard_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_charts_chart_type ON charts(chart_type)")
    
    # 时间索引表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time_index_date ON time_index(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time_index_min_timestamp ON time_index(min_timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time_index_max_timestamp ON time_index(max_timestamp)")
    
    # 资产索引表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_index_market ON asset_index(market)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asset_index_last_updated ON asset_index(last_updated)")
    
    # 查询缓存表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query_cache_query_type ON query_cache(query_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query_cache_expires_at ON query_cache(expires_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_query_cache_last_accessed ON query_cache(last_accessed)")
    
    # 系统日志表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_module ON system_logs(module)")
    
    # 审计日志表索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)")
    
    # 插入默认数据
    print("插入默认数据...")
    
    # 插入默认管理员用户（密码：admin123）
    conn.execute("""
    INSERT OR IGNORE INTO users (username, email, password_hash, role)
    VALUES ('admin', 'admin@tdxview.com', 
            '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'admin')
    """)
    
    # 插入默认数据源配置
    default_source = {
        "api_url": "https://api.tdxdata.com",
        "api_key": "",
        "timeout": 30,
        "retry_count": 3,
        "rate_limit": 100
    }
    
    conn.execute("""
    INSERT OR IGNORE INTO data_sources (name, type, config)
    VALUES ('tdxdata_default', 'tdxdata', ?)
    """, [json.dumps(default_source)])
    
    # 插入内置技术指标
    builtin_indicators = [
        {
            "name": "sma",
            "display_name": "简单移动平均线",
            "category": "trend",
            "description": "简单移动平均线，用于识别价格趋势",
            "parameters": {"period": 20},
            "is_builtin": True
        },
        {
            "name": "ema",
            "display_name": "指数移动平均线",
            "category": "trend",
            "description": "指数移动平均线，对近期价格给予更高权重",
            "parameters": {"period": 20},
            "is_builtin": True
        },
        {
            "name": "rsi",
            "display_name": "相对强弱指数",
            "category": "momentum",
            "description": "衡量价格变动速度和幅度的动量指标",
            "parameters": {"period": 14},
            "is_builtin": True
        },
        {
            "name": "macd",
            "display_name": "MACD指标",
            "category": "trend",
            "description": "移动平均收敛发散指标，用于趋势跟踪",
            "parameters": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            "is_builtin": True
        },
        {
            "name": "bollinger_bands",
            "display_name": "布林带",
            "category": "volatility",
            "description": "显示价格波动范围的通道指标",
            "parameters": {"period": 20, "std_dev": 2},
            "is_builtin": True
        },
        {
            "name": "volume",
            "display_name": "成交量",
            "category": "volume",
            "description": "成交量分析",
            "parameters": {},
            "is_builtin": True
        },
        {
            "name": "rps",
            "display_name": "相对价格强度",
            "category": "momentum",
            "description": "相对价格强度，用于比较不同资产的相对表现",
            "parameters": {"period": 20},
            "is_builtin": True
        }
    ]
    
    for indicator in builtin_indicators:
        conn.execute("""
        INSERT OR IGNORE INTO indicators 
        (name, display_name, category, description, parameters, is_builtin)
        VALUES (?, ?, ?, ?, ?, ?)
        """, [
            indicator["name"],
            indicator["display_name"],
            indicator["category"],
            indicator["description"],
            json.dumps(indicator["parameters"]),
            indicator["is_builtin"]
        ])
    
    # 创建默认仪表板
    default_dashboard = {
        "name": "默认仪表板",
        "description": "系统默认仪表板",
        "layout": {
            "type": "grid",
            "columns": 12,
            "row_height": 30
        },
        "widgets": [
            {
                "id": "price_chart",
                "type": "candlestick",
                "title": "价格图表",
                "symbol": "000001.SZ",
                "position": {"x": 0, "y": 0, "w": 12, "h": 8}
            },
            {
                "id": "volume_chart",
                "type": "bar",
                "title": "成交量",
                "symbol": "000001.SZ",
                "position": {"x": 0, "y": 8, "w": 12, "h": 4}
            },
            {
                "id": "indicator_panel",
                "type": "indicators",
                "title": "技术指标",
                "position": {"x": 0, "y": 12, "w": 12, "h": 4}
            }
        ]
    }
    
    # 获取管理员用户ID
    admin_id = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if admin_id:
        admin_id = admin_id[0]
        conn.execute("""
        INSERT OR IGNORE INTO dashboards (user_id, name, description, layout, widgets, is_default)
        VALUES (?, ?, ?, ?, ?, TRUE)
        """, [
            admin_id,
            default_dashboard["name"],
            default_dashboard["description"],
            json.dumps(default_dashboard["layout"]),
            json.dumps(default_dashboard["widgets"])
        ])
    
    # 提交事务
    conn.commit()
    
    # 显示统计信息
    print("\n数据库初始化完成！")
    print("=" * 50)
    
    # 查询表统计
    tables = [
        "users", "data_sources", "indicators", "dashboards", 
        "charts", "time_index", "asset_index", "query_cache",
        "system_logs", "audit_logs"
    ]
    
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:20s}: {count} 条记录")
    
    # 关闭连接
    conn.close()
    
    print("=" * 50)
    print(f"数据库文件: {db_path}")
    print(f"数据目录: {data_dir}")
    print(f"缓存目录: {cache_dir}")
    print("\n默认管理员账户:")
    print("  用户名: admin")
    print("  密码: admin123")
    print("\n请及时修改默认密码！")

if __name__ == "__main__":
    init_database()