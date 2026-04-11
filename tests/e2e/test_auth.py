import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import TEST_USERNAME, TEST_PASSWORD
from tests.e2e.pages.login_page import LoginPage


pytestmark = pytest.mark.critical


class TestAuth:
    def test_login_success(self, page):
        login = LoginPage(page)
        login.login(TEST_USERNAME, TEST_PASSWORD)
        login.expect_logged_in(TEST_USERNAME)

    def test_login_wrong_password(self, page):
        login = LoginPage(page)
        login.login(TEST_USERNAME, "wrongpassword")
        login.expect_login_error()

    def test_logout(self, authed_page):
        sidebar = authed_page.locator("[data-testid='stSidebar']")
        sidebar.get_by_role("button", name="退出登录").click()
        authed_page.wait_for_timeout(3000)
        expect(authed_page.get_by_role("tab", name="登录")).to_be_visible()

    def test_welcome_page_before_login(self, page):
        expect(page.get_by_text("欢迎使用 tdxview")).to_be_visible()

    def test_login_register_tab_switch(self, page):
        page.get_by_role("tab", name="注册").click()
        page.wait_for_timeout(1000)
        expect(page.get_by_text("确认密码")).to_be_visible()
        page.get_by_role("tab", name="登录").click()
        page.wait_for_timeout(1000)
        sidebar = page.locator("[data-testid='stSidebar']")
        expect(sidebar.locator('input[type="text"]').first).to_be_visible()
