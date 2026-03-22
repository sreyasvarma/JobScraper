"""
Rippling Jobs scraper — scrapes ats.rippling.com job links embedded in /careers/open-roles.
Job card structure: <a href="ats.rippling.com/rippling/jobs/{uuid}">
  <p>Job Title</p>
  <p>Department</p>
  <div>...location text...</div>
</a>
"""

import logging
from bs4 import BeautifulSoup
from .base import BaseScraper, Job
from .generic import HEADERS, _filter_jobs

logger = logging.getLogger(__name__)


class RipplingScraper(BaseScraper):
    def __init__(self, config: dict):
        self.company = config.get("name", "Rippling")
        self.url = config.get("url", "https://www.rippling.com/careers/open-roles")

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

        for el in soup.select("a[href*='ats.rippling.com/rippling/jobs/']"):
            job_url = el.get("href", "")
            if not job_url or job_url in seen_urls:
                continue
            seen_urls.add(job_url)

            # Title: first <p> in the card
            p_el = el.select_one("p")
            if p_el:
                title = p_el.get_text(strip=True)
            else:
                lines = [l.strip() for l in el.get_text(separator="\n").split("\n") if l.strip()]
                title = lines[0] if lines else ""

            if not title or len(title) < 4:
                continue

            # Location: card text is Title \n Dept \n Location
            lines = [l.strip() for l in el.get_text(separator="\n").split("\n") if l.strip()]
            location = lines[2] if len(lines) >= 3 else ""

            jobs.append(Job(title=title, url=job_url, company=self.company, location=location))

        filtered = _filter_jobs(jobs, self.url)
        logger.info(f"Rippling total: {len(filtered)} jobs")
        return filtered
