from playwright.sync_api import Page, expect

from tests.e2e.pages.base_page import BasePage


class ConfigPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    def expect_heading(self):
        expect(self.page.get_by_role("heading", name="系统配置")).to_be_visible()

    def expect_data_source_section(self):
        expect(self.page.get_by_text("数据源管理")).to_be_visible()
