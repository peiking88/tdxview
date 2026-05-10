import pytest
from playwright.sync_api import expect

from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.data_management_page import DataManagementPage


pytestmark = pytest.mark.regression


class TestDataManagement:
    def test_data_management_page_loads(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("heading", name="数据管理")).to_be_visible()

    def test_three_tabs_exist(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("tab", name="数据获取")).to_be_visible()
        expect(authed_page.get_by_role("tab", name="Parquet 文件")).to_be_visible()
        expect(authed_page.get_by_role("tab", name="数据源列表")).to_be_visible()

    def test_fetch_tab_form_elements(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_fetch_tab()
        expect(authed_page.get_by_text("获取历史数据")).to_be_visible()

    def test_parquet_tab_switch(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_parquet_tab()
        bp.wait_for_rerun()
        expect(
            authed_page.get_by_role("heading", name="Parquet 文件浏览器").first
        ).to_be_visible()

    def test_sources_tab_switch(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_sources_tab()
        bp.wait_for_rerun()
        expect(
            authed_page.get_by_text("数据源列表", exact=True).first
        ).to_be_visible()

    def test_fetch_empty_code_error(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_fetch_tab()
        dm.fetch_data("")
        bp.wait_for_rerun(timeout=10000)
        expect(authed_page.get_by_text("请输入股票代码")).to_be_visible()
