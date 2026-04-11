from playwright.sync_api import Locator, Page


class BasePage:
    def __init__(self, page: Page):
        self.page = page

    def navigate_to(self, page_name: str):
        self.page.locator(
            "[data-testid='stRadio'] label"
        ).filter(has_text=page_name).click()
        self.page.wait_for_timeout(2000)

    def wait_for_rerun(self, timeout: int = 15000):
        self.page.wait_for_timeout(1000)
        try:
            self.page.wait_for_function(
                "() => !document.querySelector('[data-testid=\"stSpinner\"]')",
                timeout=timeout,
            )
        except Exception:
            pass

    def wait_for_plotly(self, timeout: int = 15000):
        self.page.wait_for_selector(
            ".js-plotly-plot .plotly .main-svg",
            timeout=timeout,
        )

    @property
    def sidebar(self) -> Locator:
        return self.page.locator("[data-testid='stSidebar']")

    @property
    def main_content(self) -> Locator:
        return self.page.locator("[data-testid='stAppViewContainer']")
