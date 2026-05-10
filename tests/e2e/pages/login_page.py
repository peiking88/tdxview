from playwright.sync_api import Page, expect

from tests.e2e.pages.base_page import BasePage


class LoginPage(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)

    def login(self, username: str, password: str):
        self.page.get_by_role("tab", name="登录").click()
        self.page.wait_for_timeout(500)

        sidebar = self.page.locator("[data-testid='stSidebar']")
        text_inputs = sidebar.locator('input[type="text"]').all()
        pw_inputs = sidebar.locator('input[type="password"]').all()

        text_inputs[0].fill(username)
        pw_inputs[0].fill(password)

        sidebar.get_by_role("button", name="登录").click()
        self.page.wait_for_timeout(3000)

    def expect_login_error(self):
        expect(self.page.get_by_text("用户名或密码错误")).to_be_visible()

    def expect_logged_in(self, username: str):
        expect(
            self.sidebar.get_by_text(f"欢迎, {username}")
        ).to_be_visible()
