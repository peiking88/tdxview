import pytest
from playwright.sync_api import expect

from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.dashboard_page import DashboardPage


pytestmark = pytest.mark.regression


class TestDashboard:
    def test_dashboard_heading(self, authed_page):
        dash = DashboardPage(authed_page)
        dash.expect_heading()

    def test_welcome_message(self, authed_page):
        expect(authed_page.get_by_text("欢迎, e2e_tester")).to_be_visible()

    def test_app_title(self, authed_page):
        expect(authed_page.get_by_text("tdxview 数据可视化平台")).to_be_visible()

    def test_sidebar_logo_present(self, authed_page):
        sidebar = authed_page.locator("[data-testid='stSidebar']")
        expect(sidebar.get_by_text("数据驱动决策")).to_be_visible()

    def test_sidebar_logout_button(self, authed_page):
        sidebar = authed_page.locator("[data-testid='stSidebar']")
        expect(sidebar.get_by_role("button", name="退出登录")).to_be_visible()

    def test_footer_version_info(self, authed_page):
        expect(authed_page.get_by_text("版本")).to_be_visible()
