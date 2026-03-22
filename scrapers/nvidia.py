"""
Nvidia Jobs scraper — uses Playwright to render jobs.nvidia.com (their custom careers SPA).
Nvidia moved away from Workday; the new site uses /careers/job/{id} links.
Title is in div[class*='title'], location extracted from multi-line link text.
"""

import logging
from bs4 import BeautifulSoup
from .base import BaseScraper, Job
from .generic import HEADERS, _filter_jobs, _make_absolute

logger = logging.getLogger(__name__)

BASE = "https://jobs.nvidia.com"


class NvidiaScraper(BaseScraper):
    def __init__(self, config: dict):
        self.company = config.get("name", "Nvidia")
        self.url = config.get("url", "https://jobs.nvidia.com/careers?location=india")

    def fetch_jobs(self) -> list[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Run: pip install playwright && playwright install chromium")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(self.url, wait_until="load", timeout=60000)
            page.wait_for_timeout(6000)
            try:
                html = page.content()
            except Exception:
                page.wait_for_timeout(2000)
                html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        jobs = []
        seen_urls = set()

        for el in soup.select("a[href*='/careers/job/']"):
            raw_url = el.get("href", "")
            job_url = _make_absolute(raw_url, BASE)

            if not job_url or job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            # Title is in a child element whose class contains 'title'
            title_el = el.select_one("[class*='title']")
            if title_el:
                title = title_el.get_text(strip=True)
            else:
                lines = [l.strip() for l in el.get_text(separator="\n").split("\n") if l.strip()]
                title = lines[0] if lines else ""

            if not title or len(title) < 4:
                continue

            # Link text structure: Title \n JobRef \n Location
            lines = [l.strip() for l in el.get_text(separator="\n").split("\n") if l.strip()]
            location = lines[2] if len(lines) >= 3 else (lines[1] if len(lines) >= 2 else "")

            jobs.append(Job(title=title, url=job_url, company=self.company, location=location))

        filtered = _filter_jobs(jobs, self.url)
        logger.info(f"Nvidia total: {len(filtered)} jobs")
        return filtered
