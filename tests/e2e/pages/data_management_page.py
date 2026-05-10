from playwright.sync_api import Page, expect

from tests.e2e.pages.base_page import BasePage


class DataManagementPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    def go_to_fetch_tab(self):
        self.page.get_by_role("tab", name="数据获取").click()
        self.page.wait_for_timeout(1000)

    def go_to_parquet_tab(self):
        self.page.get_by_role("tab", name="Parquet 文件").click()
        self.page.wait_for_timeout(1000)

    def go_to_sources_tab(self):
        self.page.get_by_role("tab", name="数据源列表").click()
        self.page.wait_for_timeout(1000)

    def fetch_data(self, code: str = "600519"):
        self.page.locator('input[aria-label="股票代码 (逗号分隔)"]').fill(code)
        self.page.get_by_role("button", name="获取数据").click()
        self.wait_for_rerun(timeout=30000)

    def expect_fetch_success(self):
        expect(self.page.get_by_text("获取到")).to_be_visible()

    def expect_fetch_error(self):
        expect(self.page.get_by_text("获取数据失败")).to_be_visible()

    def expect_empty_warning(self):
        expect(self.page.get_by_text("请输入股票代码")).to_be_visible()

    def paginate_next(self):
        self.page.get_by_role("button", name="下一页").click()
        self.wait_for_rerun()

    def paginate_prev(self):
        self.page.get_by_role("button", name="上一页").click()
        self.wait_for_rerun()

    def expect_parquet_list(self):
        expect(self.page.get_by_text("个股票代码")).to_be_visible()

    def expect_no_parquet(self):
        expect(self.page.get_by_text("暂无 Parquet")).to_be_visible()
