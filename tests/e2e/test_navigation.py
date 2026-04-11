import pytest
from playwright.sync_api import expect

from tests.e2e.pages.base_page import BasePage


pytestmark = pytest.mark.critical

NAV_ITEMS = [
    ("仪表板", "仪表板"),
    ("图表分析", "图表分析"),
    ("技术指标", "技术指标"),
    ("数据管理", "数据管理"),
    ("系统配置", "系统配置"),
]


class TestNavigation:
    def test_default_page_after_login(self, authed_page):
        expect(authed_page.get_by_text("欢迎, e2e_tester")).to_be_visible()

    def test_sidebar_has_all_pages(self, authed_page):
        sidebar = authed_page.locator("[data-testid='stSidebar']")
        for name, _ in NAV_ITEMS:
            expect(
                sidebar.locator("[data-testid='stRadio'] label").filter(
                    has_text=name
                )
            ).to_be_visible()

    @pytest.mark.parametrize("name,heading", NAV_ITEMS)
    def test_navigate_to_each_page(self, authed_page, name, heading):
        bp = BasePage(authed_page)
        bp.navigate_to(name)
        bp.wait_for_rerun()
        expect(
            authed_page.get_by_role("heading", name=heading)
        ).to_be_visible()

    def test_navigation_remembers_current_page(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("系统配置")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("heading", name="系统配置")).to_be_visible()

        bp.navigate_to("图表分析")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("heading", name="图表分析")).to_be_visible()
