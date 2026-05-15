import os
import subprocess
import sys
import time

import pytest
import requests
from playwright.sync_api import Browser, BrowserContext, Page

STREAMLIT_PORT = 8901
BASE_URL = f"http://localhost:{STREAMLIT_PORT}"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

SYSTEM_CHROMIUM = "/snap/chromium/current/usr/lib/chromium-browser/chrome"


def _find_chromium():
    """Locate a usable Chromium executable for Playwright."""
    candidates = [SYSTEM_CHROMIUM, "/usr/bin/chromium-browser", "/usr/bin/chromium"]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Override pytest-playwright's launch args to use system Chromium."""
    chromium_path = _find_chromium()
    if chromium_path:
        return {
            "executable_path": chromium_path,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
    return {}


def _wait_for_streamlit_server(port: int, timeout: int = 60):
    url = f"http://localhost:{port}/_stcore/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="session")
def streamlit_server():
    env = os.environ.copy()
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run",
            os.path.join(PROJECT_ROOT, "app", "main.py"),
            "--server.port", str(STREAMLIT_PORT),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    if not _wait_for_streamlit_server(STREAMLIT_PORT):
        proc.terminate()
        proc.wait(timeout=10)
        raise RuntimeError("Streamlit server failed to start within 60s")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def context(browser: Browser, streamlit_server):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    pg = context.new_page()
    pg.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_selector(
        "[data-testid='stAppViewContainer']", timeout=20000,
    )
    yield pg


def wait_for_streamlit(page: Page, timeout: int = 15000):
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stSpinner\"]')",
        timeout=timeout,
    )


def wait_for_plotly(page: Page, timeout: int = 15000):
    page.wait_for_selector(
        ".js-plotly-plot .plotly .main-svg",
        timeout=timeout,
    )


def wait_for_table(page: Page, timeout: int = 10000):
    page.wait_for_selector(
        "[data-testid='stDataFrame']",
        timeout=timeout,
    )
