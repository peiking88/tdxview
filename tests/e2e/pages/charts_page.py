from playwright.sync_api import Locator, Page, expect

from tests.e2e.pages.base_page import BasePage


class ChartsPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    def query_stock(self, code: str = "600519"):
        self.sidebar.locator('input[aria-label="股票代码"]').fill(code)
        self.sidebar.get_by_role("button", name="获取数据").click()
        self.wait_for_rerun()

    def expect_chart_visible(self):
        self.wait_for_plotly()
        expect(
            self.page.locator("[data-testid='stPlotlyChart']").first
        ).to_be_visible()

    def expect_no_chart(self):
        expect(
            self.page.locator("[data-testid='stPlotlyChart']")
        ).to_have_count(0)

    def set_date_range(self, start: str, end: str):
        self.sidebar.locator('input[aria-label="股票代码"]').fill("")
        start_inputs = self.sidebar.locator('input[aria-label="Select a date."]').all()
        if len(start_inputs) >= 2:
            start_inputs[0].fill(start)
            start_inputs[1].fill(end)

    def select_chart_type(self, chart_type: str):
        combobox = self.sidebar.locator(
            'input[aria-label^="Selected"][aria-label$="图表类型"]'
        )
        combobox.click()
        self.page.wait_for_timeout(500)
        self.page.get_by_role("option", name=chart_type).click()
        self.wait_for_rerun()
