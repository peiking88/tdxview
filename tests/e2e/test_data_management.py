import pytest
from playwright.sync_api import expect

from tests.e2e.pages.base_page import BasePage
from tests.e2e.pages.data_management_page import DataManagementPage


pytestmark = pytest.mark.regression


class TestDataManagementPageStructure:
    def test_page_loads(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("heading", name="数据管理")).to_be_visible()

    def test_four_tabs_exist(self, authed_page):
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        expect(authed_page.get_by_role("tab", name="数据导入")).to_be_visible()
        expect(authed_page.get_by_role("tab", name="导入状态")).to_be_visible()
        expect(authed_page.get_by_role("tab", name="数据浏览")).to_be_visible()
        expect(authed_page.get_by_role("tab", name="数据源列表")).to_be_visible()


class TestImportTab:
    def test_import_tab_form_elements(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_import_tab()
        # Form is inside an aria-label="数据导入" tab panel
        form = authed_page.locator('[data-testid="stForm"]')
        expect(form.get_by_text("股票代码")).to_be_visible()
        expect(form.get_by_text("数据类型")).to_be_visible()
        expect(form.get_by_text("导入模式")).to_be_visible()

    def test_import_empty_code_error(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_import_tab()
        dm.fill_symbol("")
        dm.click_import()
        bp.wait_for_rerun(timeout=10000)
        dm.expect_empty_code_error()

    def test_import_history(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_import_tab()
        dm.fill_symbol("600519")
        dm.click_import()
        bp.wait_for_rerun(timeout=30000)
        # Either success or failure (network dependent)
        expect(
            authed_page.get_by_text("导入成功").or_(
                authed_page.get_by_text("导入失败")
            )
        ).to_be_visible()


class TestStatusTab:
    def test_status_tab_loads(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_status_tab()
        # Heading inside the active tab panel
        headings = authed_page.get_by_role("heading", name="导入状态").all()
        assert len(headings) >= 1

    def test_status_tab_filter_elements(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_status_tab()
        expect(authed_page.get_by_text("股票代码筛选", exact=True)).to_be_visible()
        expect(authed_page.get_by_text("数据类型筛选", exact=True)).to_be_visible()


class TestBrowseTab:
    def test_browse_tab_loads(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_browse_tab()
        bp.wait_for_rerun()
        headings = authed_page.get_by_role("heading", name="数据浏览").all()
        assert len(headings) >= 1

    def test_browse_no_data_initial(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_browse_tab()
        bp.wait_for_rerun()
        # Either "暂无" message or a selectbox for symbols (data exists)
        page_text = authed_page.inner_text("body")
        assert "暂无" in page_text or "股票代码" in page_text


class TestSourcesTab:
    def test_sources_tab_loads(self, authed_page):
        dm = DataManagementPage(authed_page)
        bp = BasePage(authed_page)
        bp.navigate_to("数据管理")
        bp.wait_for_rerun()
        dm.go_to_sources_tab()
        bp.wait_for_rerun()
        dm.expect_source_list_visible()
