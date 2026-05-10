import pytest
from playwright.sync_api import expect

from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.charts_page import ChartsPage


pytestmark = pytest.mark.regression


class TestCharts:
    def test_kline_render(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("图表分析")
        bp.wait_for_rerun()
        charts = ChartsPage(authed_page)
        charts.query_stock("600519")
        expect(
            authed_page.get_by_text("获取数据").or_(
                authed_page.locator("[data-testid='stPlotlyChart']")
            )
        ).to_be_visible()

    def test_empty_code_warning(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("图表分析")
        bp.wait_for_rerun()
        charts = ChartsPage(authed_page)
        charts.query_stock("")
        charts.expect_no_chart()

    def test_chart_heading_visible(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("图表分析")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("heading", name="图表分析")).to_be_visible()

    def test_sidebar_chart_settings(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("图表分析")
        bp.wait_for_rerun()
        sidebar = authed_page.locator("[data-testid='stSidebar']")
        expect(sidebar.get_by_text("图表设置")).to_be_visible()
        expect(
            sidebar.locator('input[aria-label="股票代码"]')
        ).to_be_visible()
