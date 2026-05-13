# tdxview

A stock market data visualization platform built on [tdxdata](https://github.com/peiking88/tdxdata). It provides real-time monitoring, historical data analysis, technical indicator calculation, and interactive charting through a Streamlit web interface.

## Tech Stack

| Component           | Technology                   |
| ------------------- | ---------------------------- |
| Language            | Python 3.13                  |
| Web UI              | Streamlit                    |
| Database            | DuckDB                       |
| Time-series Storage | DuckDB (7 tables)            |
| Charting            | Plotly                       |
| Validation          | Pydantic / pydantic-settings |
| Logging             | Loguru                       |
| Auth                | bcrypt + JWT (python-jose)   |
| Data Source         | tdxdata (通达信数据接口)     |

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
│  DuckDB · DuckDBStore (7 tables)                │
│  tdxdata source (remote / local / hybrid)        │
└─────────────────────────────────────────────────┘
```

## Features

- **Authentication**: User registration, login, JWT sessions, role-based access control
- **Historical Charts**: K-line (candlestick), line, bar, heatmap with MA overlays
- **Real-time Monitoring**: Live quotes dashboard with configurable watchlists
- **Technical Indicators**: SMA, EMA, MACD, RSI, RPS, Bollinger Bands, OBV, VWAP + custom plugin indicators
- **Data Management**: 全类型数据导入（history/realtime/tick/financial/F10/basic）、增量导入、完整重导、导入状态跟踪
- **System Configuration**: Data source management, storage stats, user preferences
- **Data Retention**: Purge old data from DuckDB, cleanup system logs
- **Backup & Restore**: Timestamped tar.gz backups with integrity verification
- **Plugin Hot-Reload**: Dynamic indicator script loading with file-hash change detection
- **Performance**: Parallel multi-symbol fetching, data downsampling, in-place chart updates

## Quick Start

### One-Click Script (Recommended)

```bash
bash scripts/setup_dev.sh all
```

This single command installs dependencies, initializes the database, and starts the application.

#### Script Commands

| Command                                            | Description                                   |
| -------------------------------------------------- | --------------------------------------------- |
| `bash scripts/setup_dev.sh setup`                  | Install dependencies & initialize environment |
| `bash scripts/setup_dev.sh run`                    | Start the Streamlit application (port 8501)   |
| `bash scripts/setup_dev.sh run --port 9000`        | Start on a custom port                        |
| `bash scripts/setup_dev.sh test`                   | Run unit & integration tests                  |
| `bash scripts/setup_dev.sh test -- -k "test_data"` | Pass extra pytest arguments                   |
| `bash scripts/setup_dev.sh e2e`                    | Run E2E UI tests (Playwright)                 |
| `bash scripts/setup_dev.sh all`                    | Full setup + start application                |

#### Options (for `setup` / `all`)

| Option              | Description                      |
| ------------------- | -------------------------------- |
| `--skip-e2e`        | Skip E2E test dependencies       |
| `--skip-playwright` | Skip Playwright browser download |
| `--skip-db`         | Skip database initialization     |
| `--verbose`         | Show detailed pip output         |

### Manual Setup

<details>
<summary>Manual installation steps</summary>

#### Prerequisites

- Python 3.10+
- 通达信行情服务器 connectivity (or local TDX data files)

#### Install

```bash
pip install -r requirements.txt
```

#### Initialize Database

```bash
python3 scripts/init_database.py
```

Default admin account: `admin` / `admin123` (change after first login)

#### Run

```bash
streamlit run app/main.py
```

Open http://localhost:8501 in your browser.

</details>

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
│   ├── database.py      # DuckDB manager
│   ├── duckdb_store.py  # DuckDBStore (7 tables, replaces ParquetManager)
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
cfg/                     # 配置文件目录
output/                  # 输出文件目录
plugins/indicators/      # Custom indicator scripts
scripts/init_database.py # Database initialization
scripts/setup_dev.sh     # One-click setup/run/test script
tests/                   # Test suite (420+ passed, dual-mode architecture)
tests/e2e/               # E2E UI tests with Playwright (46 passed)
```

## Testing

### Unit & Integration Tests

```bash
# Run all tests (auto-detect TDX server, fallback to mock)
pytest tests/ --cov=app --cov-report=term-missing

# Force mock mode (offline, no network needed)
TDX_LIVE=0 pytest tests/ -q

# Force real TDX server
TDX_LIVE=1 pytest tests/ -q

# Core business code coverage: 87.61%
# Excludes: Streamlit UI components, third-party adapters, main entry point
```

**Test Coverage Status**:

- **Total tests**: 411 passed (337 unit + 74 integration)
- **Core business code coverage**: 85.97%
- **Coverage configuration**: Excludes UI components (`app/components/*`), third-party adapters (`tdxdata_source.py`), and main entry point (`main.py`)
- **Test categories**: Unit tests for services, data layer, utilities, and integration tests
- **Quality gates**: 80% minimum coverage required (configured in pyproject.toml)

### E2E UI Tests (Playwright)

End-to-end browser tests that launch a real Streamlit server and validate the full user flow through the UI.

```bash
# Setup (one-time)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest-playwright requests

# Initialize database
python scripts/init_database.py

# Run E2E tests (使用系统 Chromium)
pytest tests/e2e/ -v --timeout=180
```

**E2E Test Status**:

- **Total**: 46 tests, all passed
- **Duration**: ~5 minutes
- **Browser**: Chromium (headless)
- **Architecture**: Page Object Model (POM) with 7 page objects, 6 test files
- **Browser**: Chromium (系统 snap 安装)
- **Test categories**:
  - **Auth** (5): login, logout, wrong password, tab switch, welcome page
  - **Navigation** (8): page routing, sidebar navigation, state persistence
  - **Charts** (4): K-line render, empty code, heading, sidebar settings
  - **Indicators** (12): 8 indicator parametrized, overlay toggle, state switch, info display
  - **Data Management** (10): 4-tab layout (导入/状态/浏览/数据源), 全类型导入, 状态查询, 数据浏览
  - **Dashboard** (6): heading, welcome, title, logo, logout, footer
- **Markers**: `@pytest.mark.critical` (auth, nav), `@pytest.mark.regression` (charts, indicators, data)

### Dual-Mode Testing Architecture

The test suite uses a **dual-mode** approach for both `get_settings` and `TDX data source`:

- **`test_settings`** (session, autouse): Creates a real `Settings()` instance pointing to temp directories. Automatically patches `get_settings` across all 18 application modules — no test file needs to mock settings manually.
- **`tdx_source`** (session): Auto-detects TDX server availability. Returns real `TdxDataSource` when server is reachable, or a `MagicMock` with realistic A-share data when offline.
- **Environment control**: `TDX_LIVE=0` (force mock), `TDX_LIVE=1` (force real), or auto-detect (default).

## Configuration

Edit `config.yaml` to customize:

- Database paths (DuckDB, Parquet, cache directories)
- Cache settings (memory size, TTL)
- TDX data source (timeout, retry)
- Security settings (secret key, session timeout, password policy)
- Logging level and file path

## License

MIT

### 2026-05-13 17:30:05
```
 app/components/auth.py             |  4 ++--
 app/components/charts.py           |  6 +++---
 app/components/config.py           | 36 +++++++++++++++++++++++++-----------
 app/components/dashboard.py        | 23 ++++++++++++++++-------
 app/components/indicators.py       | 36 +++++++++++++++++++++++-------------
 app/data/duckdb_store.py           |  8 +++++---
 app/main.py                        | 37 ++++++++++++++-----------------------
 app/services/user_service.py       | 29 +++++++++++++++++++----------
 summary.md                         |  4 ++--
 tests/unit/test_config_and_data.py |  8 ++++----
 10 files changed, 113 insertions(+), 78 deletions(-)
```
