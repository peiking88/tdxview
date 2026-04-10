# tdxview

A stock market data visualization platform built on [tdxdata](./external/tdxdata/). It provides real-time monitoring, historical data analysis, technical indicator calculation, and interactive charting through a Streamlit web interface.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.13 |
| Web UI | Streamlit |
| Database | DuckDB |
| Time-series Storage | Parquet |
| Charting | Plotly |
| Validation | Pydantic / pydantic-settings |
| Logging | Loguru |
| Auth | bcrypt + JWT (python-jose) |
| Data Source | tdxdata (通达信数据接口) |

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Streamlit UI                    │
│  auth · charts · dashboard · indicators · config │
├─────────────────────────────────────────────────┤
│                   Services                       │
│  data · visualization · indicator · user         │
│  backup · retention · plugin                     │
├─────────────────────────────────────────────────┤
│                    Data                          │
│  DuckDB · Parquet · Cache (LRU + Disk)           │
│  tdxdata source (remote / local / hybrid)        │
└─────────────────────────────────────────────────┘
```

## Features

- **Authentication**: User registration, login, JWT sessions, role-based access control
- **Historical Charts**: K-line (candlestick), line, bar, heatmap with MA overlays
- **Real-time Monitoring**: Live quotes dashboard with configurable watchlists
- **Technical Indicators**: SMA, EMA, MACD, RSI, RPS, Bollinger Bands, OBV, VWAP + custom plugin indicators
- **Data Management**: Fetch, store to Parquet, browse local data files
- **System Configuration**: Data source management, cache settings, user preferences
- **Data Retention**: Archive/purge old Parquet files, cleanup expired cache and logs
- **Backup & Restore**: Timestamped tar.gz backups with integrity verification
- **Plugin Hot-Reload**: Dynamic indicator script loading with file-hash change detection
- **Performance**: Parallel multi-symbol fetching, data downsampling, in-place chart updates

## Quick Start

### Prerequisites

- Python 3.10+
-通达信行情服务器 connectivity (or local TDX data files)

### Install

```bash
pip install -r requirements.txt
```

### Initialize Database

```bash
python3 scripts/init_database.py
```

Default admin account: `admin` / `admin123` (change after first login)

### Run

```bash
streamlit run app/main.py
```

Open http://localhost:8501 in your browser.

### Docker

```bash
docker build -t tdxview .
docker run -p 8501:8501 tdxview
```

## Project Structure

```
app/
├── components/          # Streamlit UI pages
│   ├── auth.py          # Login/register
│   ├── charts.py        # Chart visualization
│   ├── dashboard.py     # Monitoring dashboard
│   ├── data_management.py
│   ├── indicators.py
│   └── config.py
├── config/
│   └── settings.py      # Pydantic settings (config.yaml)
├── data/
│   ├── cache.py         # MemoryCache (LRU+TTL) + DiskCache + CacheManager
│   ├── database.py      # DuckDB manager
│   ├── parquet_manager.py
│   ├── models/          # Pydantic data models
│   └── sources/
│       ├── base_source.py
│       └── tdxdata_source.py
├── services/
│   ├── data_service.py         # Data orchestration + parallel queries
│   ├── visualization_service.py # Chart creation + advanced features
│   ├── indicator_service.py    # Indicator calculation engine
│   ├── user_service.py         # Auth, JWT, user CRUD
│   ├── backup_service.py       # Backup automation & restore
│   ├── retention_service.py    # Data retention & archival
│   └── plugin_service.py       # Plugin hot-reload
├── utils/
│   ├── indicators/      # Built-in indicator implementations
│   │   ├── trend.py     # SMA, EMA, MACD
│   │   ├── momentum.py  # RSI, RPS
│   │   ├── volatility.py # Bollinger Bands
│   │   ├── volume.py    # OBV, VWAP
│   │   └── custom.py    # Custom indicator loader
│   └── logging.py       # Loguru setup
└── main.py              # Streamlit app entry

config.yaml              # Application configuration
plugins/indicators/      # Custom indicator scripts
scripts/init_database.py # Database initialization
tests/                   # Test suite (518 passed, 94% coverage)
external/tdxdata/        # Third-party data library (read-only)
```

## Testing

```bash
# Run all tests with coverage report
pytest tests/ --cov=app --cov-report=term-missing

# Core business code coverage: 94%
# Excludes: Streamlit UI components, third-party adapters, main entry point
```

**Test Coverage Status**:
- **Total tests**: 518 passed
- **Core business code coverage**: 94%
- **Coverage configuration**: Excludes UI components (`app/components/*`), third-party adapters (`tdxdata_source.py`), and main entry point (`main.py`)
- **Test categories**: Unit tests for services, data layer, utilities, and integration tests
- **Quality gates**: 80% minimum coverage required (configured in pyproject.toml)

## Configuration

Edit `config.yaml` to customize:

- Database paths (DuckDB, Parquet, cache directories)
- Cache settings (memory size, TTL)
- TDX data source (timeout, retry)
- Security settings (secret key, session timeout, password policy)
- Logging level and file path

## License

MIT
