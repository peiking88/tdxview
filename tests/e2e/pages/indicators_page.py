from playwright.sync_api import Page, expect

from tests.e2e.pages.base_page import BasePage


class IndicatorsPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    def select_indicator(self, name: str):
        combobox = self.sidebar.locator(
            'input[aria-label$="选择指标"]'
        )
        combobox.click()
        self.page.wait_for_timeout(500)
        self.page.get_by_role("option", name=name).click()
        self.wait_for_rerun()

    def calculate(self):
        self.sidebar.get_by_role("button", name="计算指标").click()
        self.wait_for_rerun()

    def toggle_overlay(self, checked: bool = True):
        checkbox = self.sidebar.get_by_label("叠加到K线")
        if checked:
            checkbox.check()
        else:
            checkbox.uncheck()

    def expect_indicator_chart(self):
        self.wait_for_plotly()
        expect(
            self.page.locator("[data-testid='stPlotlyChart']")
        ).to_be_visible()

    def expect_overlay_mode(self):
        self.wait_for_plotly()
        expect(
            self.page.locator("[data-testid='stPlotlyChart']")
        ).to_have_count(1)

    def expect_separate_mode(self):
        self.wait_for_plotly()
        expect(
            self.page.locator("[data-testid='stPlotlyChart']")
        ).to_be_visible()

    def expand_stats(self):
        self.page.get_by_role("button", name="指标数值").click()

    def expect_stats_visible(self):
        expect(self.page.get_by_text("最新值")).to_be_visible()

    def set_symbol(self, code: str):
        self.sidebar.locator('input[aria-label="股票代码"]').fill(code)
