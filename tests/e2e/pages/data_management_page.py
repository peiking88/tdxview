from playwright.sync_api import Page, expect

from tests.e2e.pages.base_page import BasePage


class DataManagementPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    # -- Tab navigation --

    def go_to_import_tab(self):
        self.page.get_by_role("tab", name="数据导入").click()
        self.page.wait_for_timeout(1000)

    def go_to_status_tab(self):
        self.page.get_by_role("tab", name="导入状态").click()
        self.page.wait_for_timeout(1000)

    def go_to_browse_tab(self):
        self.page.get_by_role("tab", name="数据浏览").click()
        self.page.wait_for_timeout(1000)

    def go_to_sources_tab(self):
        self.page.get_by_role("tab", name="数据源列表").click()
        self.page.wait_for_timeout(1000)

    # -- Import tab --

    def fill_symbol(self, code: str):
        # Scope to the import form to avoid matching status tab's filter input
        form = self.page.locator('[data-testid="stForm"]')
        form.locator('input[aria-label="股票代码"]').fill(code)

    def select_data_type(self, type_name: str):
        self.page.locator('label').filter(has_text=type_name).click()
        self.page.wait_for_timeout(500)

    def click_import(self):
        self.page.get_by_role("button", name="导入").click()
        self.wait_for_rerun(timeout=30000)

    def expect_import_success(self):
        expect(self.page.get_by_text("导入成功")).to_be_visible()

    def expect_import_failure(self, msg: str = "导入失败"):
        expect(self.page.get_by_text(msg)).to_be_visible()

    def expect_empty_code_error(self):
        expect(self.page.get_by_text("请输入股票代码")).to_be_visible()

    # -- Status tab --

    def expect_status_table_visible(self):
        expect(self.page.get_by_text("导入状态")).to_be_visible()

    def expect_no_import_records(self):
        expect(self.page.get_by_text("暂无导入记录")).to_be_visible()

    # -- Browse tab --

    def select_browse_type(self, type_name: str):
        # The browse tab has its own data type dropdown
        self.page.locator('[data-testid="stSelectbox"]').filter(has_text="数据类型").locator("input").click()
        self.page.get_by_text(type_name, exact=True).click()
        self.page.wait_for_timeout(1000)

    def expect_browse_data(self):
        expect(self.page.get_by_text("记录数")).to_be_visible()

    def expect_no_browse_data(self, type_name: str):
        expect(self.page.get_by_text(f"暂无 {type_name} 数据")).to_be_visible()

    # -- Sources tab --

    def expect_source_list_visible(self):
        expect(self.page.get_by_text("数据源列表").first).to_be_visible()
