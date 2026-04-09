"""
应用配置管理
基于Pydantic Settings的配置管理
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class DatabaseConfig(BaseModel):
    """数据库配置"""
    duckdb_path: str = Field(default="data/tdxview.db")
    parquet_dir: str = Field(default="data/parquet")
    cache_dir: str = Field(default="data/cache")
    max_connections: int = Field(default=10)
    connection_timeout: int = Field(default=30)
    wal_mode: bool = Field(default=True)


class TdxDataConfig(BaseModel):
    """tdxdata配置"""
    api_url: str = Field(default="https://api.tdxdata.com")
    api_key: str = Field(default="")
    timeout: int = Field(default=30)
    retry_count: int = Field(default=3)
    rate_limit: int = Field(default=100)
    cache_ttl: int = Field(default=300)


class CacheConfig(BaseModel):
    """缓存配置"""
    memory_enabled: bool = Field(default=True)
    memory_max_size_mb: int = Field(default=100)
    memory_default_ttl: int = Field(default=300)
    
    disk_enabled: bool = Field(default=True)
    disk_max_size_gb: int = Field(default=10)
    disk_compression: bool = Field(default=True)
    
    query_enabled: bool = Field(default=True)
    query_ttl: int = Field(default=3600)
    query_max_items: int = Field(default=1000)


class IndicatorConfig(BaseModel):
    """指标配置"""
    builtin_path: str = Field(default="app/utils/indicators")
    custom_path: str = Field(default="plugins/indicators")
    cache_enabled: bool = Field(default=True)
    cache_ttl: int = Field(default=600)
    parallel_calculation: bool = Field(default=True)
    max_workers: int = Field(default=4)


class SecurityConfig(BaseModel):
    """安全配置"""
    authentication_enabled: bool = Field(default=True)
    session_timeout: int = Field(default=86400)
    password_min_length: int = Field(default=8)
    password_require_special: bool = Field(default=True)
    
    authorization_enabled: bool = Field(default=True)
    default_role: str = Field(default="user")
    roles: List[str] = Field(default=["user", "admin"])
    
    secret_key: str = Field(default="changemeinproduction")
    
    @validator("secret_key")
    def validate_secret_key(cls, v):
        if v == "changemeinproduction":
            import warnings
            warnings.warn("使用默认密钥，生产环境请修改！")
        return v


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = Field(default="INFO")
    format: str = Field(default="json")
    
    file_enabled: bool = Field(default=True)
    file_path: str = Field(default="logs/tdxview.log")
    file_max_size_mb: int = Field(default=100)
    file_backup_count: int = Field(default=5)
    file_compress: bool = Field(default=True)
    
    console_enabled: bool = Field(default=True)
    console_color: bool = Field(default=True)
    
    access_log_enabled: bool = Field(default=True)
    access_log_format: str = Field(
        default='${time} ${status} ${method} ${path} ${latency}'
    )


class AppConfig(BaseModel):
    """应用配置"""
    name: str = Field(default="tdxview")
    version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8501)
    workers: int = Field(default=1)


class Settings(BaseSettings):
    """应用设置"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore"
    )
    
    # 环境
    environment: str = Field(default="development")
    
    # 各模块配置
    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    tdxdata: TdxDataConfig = Field(default_factory=TdxDataConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    indicators: IndicatorConfig = Field(default_factory=IndicatorConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    # 从YAML文件加载配置
    @classmethod
    def from_yaml(cls, yaml_path: Optional[str] = None):
        """从YAML文件加载配置"""
        if yaml_path is None:
            yaml_path = os.getenv("CONFIG_FILE", "config.yaml")
        
        config_dict = {}
        if Path(yaml_path).exists():
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config_dict.update(yaml_config)
        
        # 应用环境特定配置
        environment = config_dict.get("environment", os.getenv("ENVIRONMENT", "development"))
        env_config = config_dict.get("environments", {}).get(environment, {})
        
        # 合并配置
        if env_config:
            # 深度合并配置
            def deep_merge(base, update):
                for key, value in update.items():
                    if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                        deep_merge(base[key], value)
                    else:
                        base[key] = value
                return base
            
            config_dict = deep_merge(config_dict, env_config)
        
        return cls(**config_dict)
    
    @validator("environment")
    def validate_environment(cls, v):
        valid_environments = ["development", "production", "testing"]
        if v not in valid_environments:
            raise ValueError(f"环境必须是: {', '.join(valid_environments)}")
        return v


# 全局设置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局设置实例"""
    global _settings
    if _settings is None:
        _settings = Settings.from_yaml()
    return _settings


def reload_settings():
    """重新加载设置"""
    global _settings
    _settings = Settings.from_yaml()
    return _settings


# 配置验证和工具函数
def validate_config():
    """验证配置"""
    settings = get_settings()
    
    # 检查必要目录
    required_dirs = [
        settings.database.parquet_dir,
        settings.database.cache_dir,
        Path(settings.logging.file_path).parent
    ]
    
    for dir_path in required_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    # 检查数据库文件
    db_path = Path(settings.database.duckdb_path)
    if not db_path.exists():
        import warnings
        warnings.warn(f"数据库文件不存在: {db_path}")
    
    # 检查API密钥
    if not settings.tdxdata.api_key:
        import warnings
        warnings.warn("未配置tdxdata API密钥")
    
    return True


def get_config_summary() -> Dict[str, Any]:
    """获取配置摘要"""
    settings = get_settings()
    
    return {
        "app": {
            "name": settings.app.name,
            "version": settings.app.version,
            "debug": settings.app.debug,
            "environment": settings.environment
        },
        "database": {
            "path": settings.database.duckdb_path,
            "parquet_dir": settings.database.parquet_dir
        },
        "tdxdata": {
            "api_url": settings.tdxdata.api_url,
            "api_key_set": bool(settings.tdxdata.api_key)
        },
        "security": {
            "authentication_enabled": settings.security.authentication_enabled,
            "authorization_enabled": settings.security.authorization_enabled
        },
        "logging": {
            "level": settings.logging.level,
            "file_enabled": settings.logging.file_enabled
        }
    }


if __name__ == "__main__":
    # 测试配置加载
    settings = get_settings()
    print("配置加载成功!")
    print(f"应用: {settings.app.name} v{settings.app.version}")
    print(f"环境: {settings.environment}")
    print(f"调试模式: {settings.app.debug}")
    print(f"数据库: {settings.database.duckdb_path}")
    
    # 验证配置
    validate_config()