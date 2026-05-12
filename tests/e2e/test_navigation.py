import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.critical

NAV_ITEMS = [
    ("图表分析", "图表分析"),
    ("技术指标", "技术指标"),
    ("系统管理", "系统管理"),
]


class TestNavigation:
    def test_default_page(self, page):
        expect(page.get_by_role("heading", name="图表分析")).to_be_visible()

    def test_sidebar_has_all_pages(self, page):
        sidebar = page.locator("[data-testid='stSidebar']")
        for name, _ in NAV_ITEMS:
            expect(
                sidebar.get_by_role("button", name=name)
            ).to_be_visible()

    @pytest.mark.parametrize("name,heading", NAV_ITEMS)
    def test_navigate_to_each_page(self, page, name, heading):
        sidebar = page.locator("[data-testid='stSidebar']")
        sidebar.get_by_role("button", name=name).click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        expect(
            page.get_by_role("heading", name=heading)
        ).to_be_visible()

    def test_navigation_remembers_current_page(self, page):
        sidebar = page.locator("[data-testid='stSidebar']")
        sidebar.get_by_role("button", name="系统管理").click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        expect(page.get_by_role("heading", name="系统管理")).to_be_visible()

        sidebar.get_by_role("button", name="图表分析").click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        expect(page.get_by_role("heading", name="图表分析")).to_be_visible()
