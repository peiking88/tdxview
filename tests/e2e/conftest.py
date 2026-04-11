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

TEST_USERNAME = "e2e_tester"
TEST_PASSWORD = "Test!1234"


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


def _ensure_test_user():
    os.chdir(PROJECT_ROOT)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    from app.data.database import DatabaseManager
    from app.services.user_service import hash_password

    db_path = os.path.join(PROJECT_ROOT, "data", "tdxview.db")
    db = DatabaseManager(db_path=db_path)
    try:
        row = db.fetch_one(
            "SELECT id FROM users WHERE username = ?", [TEST_USERNAME]
        )
        if row:
            db.execute(
                "UPDATE users SET password_hash = ?, is_active = TRUE WHERE username = ?",
                [hash_password(TEST_PASSWORD), TEST_USERNAME],
            )
        else:
            db.execute(
                "INSERT INTO users (username, email, password_hash, role, is_active, preferences) "
                "VALUES (?, ?, ?, 'admin', TRUE, ?)",
                [TEST_USERNAME, "e2e@test.com", hash_password(TEST_PASSWORD), "{}"],
            )
        db.connection.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def streamlit_server():
    _ensure_test_user()

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


@pytest.fixture
def authed_page(page: Page) -> Page:
    from tests.e2e.pages.login_page import LoginPage
    login = LoginPage(page)
    login.login(TEST_USERNAME, TEST_PASSWORD)
    yield page


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
