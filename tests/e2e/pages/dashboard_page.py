from playwright.sync_api import Page, expect

from tests.e2e.pages.base_page import BasePage


class DashboardPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    def expect_heading(self):
        expect(self.page.get_by_role("heading", name="仪表板")).to_be_visible()

    def expect_system_metrics(self):
        expect(self.page.get_by_text("CPU")).to_be_visible()

    def expect_data_source_table(self):
        expect(self.page.get_by_text("数据源")).to_be_visible()
