"""
Apple Jobs scraper — uses Playwright to render the Apple Jobs SPA.
Apple's direct API (jobs.apple.com/api/role/search) redirects bot requests to a 404 page,
so we load the React SPA with a real browser and extract job links from the rendered HTML.
"""

import logging
from bs4 import BeautifulSoup
from .base import BaseScraper, Job
from .generic import _scrape_soup, HEADERS

logger = logging.getLogger(__name__)


class AppleScraper(BaseScraper):
    """
    Scraper for Apple careers using Playwright to render the SPA.
    """

    company = "Apple"

    def __init__(self, config: dict):
        self.company = config.get("name", "Apple")
        self.url = config.get("url", "https://jobs.apple.com/en-in/search")

    def fetch_jobs(self) -> list[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Run: pip install playwright && playwright install chromium")

        selectors = {
            "container": "a[href*='/details/']",
            "title": "a[href*='/details/']",
            "location": "span[class*='location'], td[class*='location'], div[class*='location']",
        }

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(self.url, wait_until="load", timeout=60000)
            page.wait_for_timeout(4000)
            try:
                html = page.content()
            except Exception:
                page.wait_for_timeout(2000)
                html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        jobs = _scrape_soup(soup, selectors, self.url, self.company)
        logger.info(f"Apple total: {len(jobs)} jobs")
        return jobs
