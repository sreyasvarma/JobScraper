"""
Generic scraper — works for any company entry in config.yaml.
Routes Apple to a dedicated API-based scraper automatically.
"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from .base import BaseScraper, Job

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Junk filtering ──────────────────────────────────────────────────────────────

JUNK_PATTERNS = [
    r"^(careers?|jobs?|work with us|join us|our team|life at|working at)$",
    r"^(home|about|contact|privacy|terms|cookies?|sitemap|faq|help|support)$",
    r"^(sign in|log in|login|register|apply now|learn more|read more|view all)$",
    r"^(opens? in a new (window|tab))$",
    r"(e-verify|accommodation|disability|equal opportunity|eeo|affirmative action)",
    r"(drug.free|background check|reasonable accommodation)",
    r"^(search|filter|sort|results?|page \d+|\d+ results?)$",
    r"(cookie|privacy policy|terms of (service|use)|legal notice)",
    r"^(follow us|connect with|share|tweet|linkedin|facebook|instagram|twitter)$",
    r"(work-life balance|benefits?|perks?|culture|values?|mission|vision)",
    r"^[\d\s\-\(\)\+\.]{5,}$",
    r"^.{0,3}$",
    r"^.{150,}$",
]

JOB_TITLE_SIGNALS = [
    "engineer", "developer", "designer", "manager", "director", "analyst",
    "scientist", "researcher", "architect", "lead", "senior", "junior", "staff",
    "intern", "associate", "specialist", "consultant", "recruiter", "coordinator",
    "product", "marketing", "sales", "finance", "legal", "operations", "devops",
    "backend", "frontend", "fullstack", "full-stack", "mobile", "ios", "android",
    "data", "machine learning", "ai", "ml", "security", "infra", "infrastructure",
    "sre", "qa", "quality", "support", "success", "growth", "hr", "people",
    "content", "writer", "editor", "brand", "account", "software", "hardware",
    "program", "project", "head of", "vp ", "principal",
]

JOB_URL_SIGNALS = [
    "/jobs/", "/job/", "/careers/", "/career/", "/opening", "/position",
    "/role/", "/apply", "/listing", "/postings/", "/details/",
    "lever.co", "greenhouse.io", "ashbyhq.com", "workable.com",
    "myworkdayjobs.com", "icims.com", "jobvite.com", "smartrecruiters.com",
]

JUNK_URL_PATTERNS = [
    "/about", "/culture", "/benefits", "/perks", "/team", "/blog",
    "/news", "/press", "/legal", "/privacy", "/terms", "/cookie",
    "/contact", "/help", "/support", "/faq", "/sitemap",
    "facebook.com", "twitter.com", "linkedin.com", "instagram.com",
    "youtube.com", "mailto:", "tel:", "#",
]


def _is_junk_title(title: str) -> bool:
    t = title.strip().lower()
    for pattern in JUNK_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return True
    return False


def _is_junk_url(url: str, base_url: str) -> bool:
    if not url:
        return True
    url_lower = url.lower()
    if url.rstrip("/") == base_url.rstrip("/"):
        return True
    for pattern in JUNK_URL_PATTERNS:
        if pattern in url_lower:
            return True
    return False


def _job_title_score(title: str, url: str) -> int:
    score = 0
    t = title.lower()
    u = url.lower()
    for sig in JOB_URL_SIGNALS:
        if sig in u:
            score += 3
            break
    for sig in JOB_TITLE_SIGNALS:
        if sig in t:
            score += 2
            break
    if 15 <= len(title) <= 80:
        score += 1
    words = title.split()
    if 2 <= len(words) <= 8:
        score += 1
    if _is_junk_title(title):
        score -= 10
    if _is_junk_url(url, ""):
        score -= 5
    return score


def _filter_jobs(jobs: list[Job], base_url: str) -> list[Job]:
    candidates = []
    for job in jobs:
        if _is_junk_title(job.title):
            logger.debug(f"Filtered junk title: {job.title!r}")
            continue
        if _is_junk_url(job.url, base_url):
            logger.debug(f"Filtered junk URL: {job.url!r}")
            continue
        candidates.append(job)

    if not candidates:
        return []

    scored = [(job, _job_title_score(job.title, job.url)) for job in candidates]
    scored.sort(key=lambda x: -x[1])
    high_conf = [job for job, score in scored if score >= 3]
    if high_conf:
        logger.info(f"Returning {len(high_conf)} high-confidence jobs (from {len(jobs)} raw)")
        return high_conf
    ok = [job for job, score in scored if score >= 0]
    logger.info(f"Returning {len(ok)} jobs score>=0 (from {len(jobs)} raw)")
    return ok


def _make_absolute(url: str, base: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    return urljoin(base, url)


def _extract_text(element, selectors: list[str]) -> str:
    for sel in selectors:
        if not sel.strip():
            continue
        found = element.select_one(sel.strip())
        if found:
            return found.get_text(strip=True)
    return element.get_text(strip=True)[:120]


def _scrape_soup(soup: BeautifulSoup, selectors: dict, base_url: str, company: str) -> list[Job]:
    container_sel = selectors.get("container", "a")
    title_sels = [s.strip() for s in selectors.get("title", "").split(",") if s.strip()]
    location_sels = [s.strip() for s in selectors.get("location", "").split(",") if s.strip()]

    raw_jobs = []
    seen_urls = set()
    seen_titles = set()

    for el in soup.select(container_sel):
        link_el = el if el.name == "a" else el.find("a")
        raw_url = link_el.get("href", "") if link_el else ""
        job_url = _make_absolute(raw_url, base_url)

        if job_url and job_url in seen_urls:
            continue
        if job_url:
            seen_urls.add(job_url)

        title = _extract_text(el, title_sels) if title_sels else el.get_text(strip=True)[:80]
        title = title.strip()

        title_key = title.lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        if not title or len(title) < 4:
            continue

        location = _extract_text(el, location_sels) if location_sels else ""
        if location == title:
            location = ""

        raw_jobs.append(Job(
            title=title,
            url=job_url,
            company=company,
            location=location,
        ))

    return _filter_jobs(raw_jobs, base_url)


class GenericStaticScraper(BaseScraper):
    def __init__(self, config: dict):
        self.company = config["name"]
        self.url = config["url"]
        self.selectors = config.get("selectors", {})

    def fetch_jobs(self) -> list[Job]:
        resp = requests.get(self.url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        return _scrape_soup(soup, self.selectors, self.url, self.company)


class GenericJSScraper(BaseScraper):
    def __init__(self, config: dict):
        self.company = config["name"]
        self.url = config["url"]
        self.selectors = config.get("selectors", {})

    def fetch_jobs(self) -> list[Job]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Run: pip install playwright && playwright install chromium")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(self.url, wait_until="load", timeout=60000)
            page.wait_for_timeout(5000)
            try:
                html = page.content()
            except Exception:
                page.wait_for_timeout(2000)
                html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "lxml")
        return _scrape_soup(soup, self.selectors, self.url, self.company)


def scraper_for(company_config: dict) -> BaseScraper:
    """
    Factory: pick the right scraper for a company.
    Several companies have dedicated scrapers for their custom career sites.
    Everything else uses the generic HTML scraper.
    """
    name = company_config.get("name", "").lower()
    url  = company_config.get("url", "").lower()

    if "apple" in name or "jobs.apple.com" in url:
        from .apple import AppleScraper
        return AppleScraper(company_config)

    if "nvidia" in name or "jobs.nvidia.com" in url:
        from .nvidia import NvidiaScraper
        return NvidiaScraper(company_config)

    if "rippling" in name or "ats.rippling.com" in url or "rippling.com/careers" in url:
        from .rippling import RipplingScraper
        return RipplingScraper(company_config)

    if "meta" in name or "metacareers.com" in url:
        from .meta import MetaScraper
        return MetaScraper(company_config)

    if company_config.get("type", "static") == "js":
        return GenericJSScraper(company_config)
    return GenericStaticScraper(company_config)
