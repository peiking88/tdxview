import pytest
from playwright.sync_api import expect

from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.indicators_page import IndicatorsPage


pytestmark = pytest.mark.regression

INDICATORS = [
    "SMA 简单移动平均线",
    "EMA 指数移动平均线",
    "MACD",
    "RSI 相对强弱指数",
    "RPS 相对价格强度",
    "布林带",
    "OBV 能量潮",
    "VWAP 成交量加权平均价",
]


class TestIndicators:
    def test_indicator_page_loads(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("技术指标")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("heading", name="技术指标")).to_be_visible()

    def test_sidebar_indicator_settings(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("技术指标")
        bp.wait_for_rerun()
        sidebar = authed_page.locator("[data-testid='stSidebar']")
        expect(sidebar.get_by_text("指标设置")).to_be_visible()

    @pytest.mark.parametrize("indicator", INDICATORS)
    def test_each_indicator_no_error(self, authed_page, indicator):
        ind = IndicatorsPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("技术指标")
        bp.wait_for_rerun()
        ind.select_indicator(indicator)
        ind.set_symbol("600519")
        ind.calculate()
        expect(authed_page.get_by_text("NameError")).to_be_hidden()
        expect(authed_page.get_by_text("KeyError")).to_be_hidden()

    def test_overlay_toggle_exists(self, authed_page):
        ind = IndicatorsPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("技术指标")
        bp.wait_for_rerun()
        ind.select_indicator("SMA 简单移动平均线")
        expect(
            authed_page.locator("[data-testid='stSidebar']").get_by_text("叠加到K线")
        ).to_be_visible()

    def test_indicator_switch_no_stale_state(self, authed_page):
        ind = IndicatorsPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("技术指标")
        bp.wait_for_rerun()

        ind.select_indicator("SMA 简单移动平均线")
        ind.set_symbol("600519")
        ind.calculate()

        ind.select_indicator("MACD")
        ind.set_symbol("600519")
        ind.calculate()
        expect(authed_page.get_by_text("NameError")).to_be_hidden()
        expect(authed_page.get_by_text("KeyError")).to_be_hidden()

    def test_indicator_info_display(self, authed_page):
        ind = IndicatorsPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("技术指标")
        bp.wait_for_rerun()
        ind.select_indicator("SMA 简单移动平均线")
        expect(authed_page.get_by_text("类别:")).to_be_visible()
