"""
Meta (Facebook) Careers scraper — renders metacareers.com SPA with Playwright.
Jobs are at /profile/job_details/{id}. Link inner text is multi-line:
  Line 0: Job Title
  Line 1: Location
  Line 2+: Team / category (ignored)
"""

import logging
from .base import BaseScraper, Job
from .generic import HEADERS, _filter_jobs

logger = logging.getLogger(__name__)

_JUNK_CHARS = {"\u22c5", "\u00b7", "\u2022", "\u2027"}  # ⋅ · • ‧


class MetaScraper(BaseScraper):
    def __init__(self, config: dict):
        self.company = config.get("name", "Meta")
        self.url = config.get("url", "https://www.metacareers.com/jobsearch")

    def fetch_jobs(self) -> list[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Run: pip install playwright && playwright install chromium")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(self.url, wait_until="load", timeout=60000)
            page.wait_for_timeout(9000)
            try:
                job_data = page.eval_on_selector_all(
                    "a[href*='/profile/job_details/']",
                    """els => {
                        const seen = new Set();
                        return els.reduce((acc, e) => {
                            const href = e.href.startsWith('http') ? e.href
                                : 'https://www.metacareers.com' + e.getAttribute('href');
                            if (!seen.has(href)) {
                                seen.add(href);
                                acc.push({href, text: e.innerText.trim()});
                            }
                            return acc;
                        }, []);
                    }"""
                )
            except Exception:
                page.wait_for_timeout(2000)
                job_data = page.eval_on_selector_all(
                    "a[href*='/profile/job_details/']",
                    "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))"
                )
            browser.close()

        jobs = []
        seen_urls = set()

        for item in job_data:
            url = item.get("href", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            text = item.get("text", "")
            lines = [
                l.strip() for l in text.split("\n")
                if l.strip() and l.strip() not in _JUNK_CHARS
            ]

            title = lines[0] if lines else ""
            location = lines[1] if len(lines) > 1 else ""

            if not title or len(title) < 4:
                continue

            jobs.append(Job(title=title, url=url, company=self.company, location=location))

        filtered = _filter_jobs(jobs, self.url)
        logger.info(f"Meta total: {len(filtered)} jobs")
        return filtered
