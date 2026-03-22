"""
Flask API server — exposes job data and controls to the frontend dashboard.
Run with: python api.py
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import yaml
import threading
import logging
import requests as req
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, quote_plus

from storage import JobStorage
from main import run_check, load_config

app = Flask(__name__)
CORS(app)

logger = logging.getLogger(__name__)
_check_lock = threading.Lock()

CONFIG_PATH = "config.yaml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Known ATS platforms — pre-tested selectors, very reliable
ATS_PATTERNS = {
    "greenhouse.io":    {"container": "div.job-post a, li.lw--job-listing a", "title": "p.body, h2, span", "location": "span.location, p.body--metadata"},
    "lever.co":         {"container": "a.posting-title", "title": "h5, .posting-name", "location": ".sort-by-location span"},
    "ashbyhq.com":      {"container": "a[href*='/jobs/']", "title": "h3, h2, p", "location": "p, span"},
    "workable.com":     {"container": "li[data-ui='job'] a", "title": "h3, span.role", "location": "span.location"},
    "smartrecruiters":  {"container": "li.job-item a", "title": "h4.job-title", "location": "span.job-location"},
    "myworkdayjobs":    {"container": "a[data-automation-id='jobTitle']", "title": "a[data-automation-id='jobTitle']", "location": "dd[data-automation-id='location']"},
    "icims.com":        {"container": "a[href*='icims.com/jobs']", "title": "h3, .iCIMS_JobTitle", "location": ".iCIMS_JobLocation"},
    "jobvite.com":      {"container": "a.jv-job-list-name", "title": "a.jv-job-list-name", "location": ".jv-job-list-location"},
    "breezy.hr":        {"container": "li.position a", "title": "h2, h3", "location": "li.location"},
    "bamboohr.com":     {"container": "li.ResumenoJob a", "title": "h2, .ResumenoJob-title", "location": ".ResumenoJob-location"},
}

# Canonical careers URL patterns per known company (fallback before web search)
KNOWN_CAREERS = {
    "google":       "https://careers.google.com/jobs/results/",
    "meta":         "https://www.metacareers.com/jobs",
    "microsoft":    "https://careers.microsoft.com/us/en/search-results",
    "apple":        "https://jobs.apple.com/en-us/search",
    "amazon":       "https://www.amazon.jobs/en/search",
    "netflix":      "https://jobs.netflix.com/search",
    "stripe":       "https://stripe.com/jobs",
    "linear":       "https://linear.app/careers",
    "vercel":       "https://vercel.com/careers",
    "figma":        "https://www.figma.com/careers/",
    "notion":       "https://www.notion.so/careers",
    "anthropic":    "https://www.anthropic.com/careers",
    "openai":       "https://openai.com/careers",
    "github":       "https://github.com/about/careers",
    "shopify":      "https://www.shopify.com/careers",
    "airbnb":       "https://careers.airbnb.com/",
    "uber":         "https://www.uber.com/us/en/careers/",
    "lyft":         "https://www.lyft.com/careers",
    "coinbase":     "https://www.coinbase.com/careers/positions",
    "discord":      "https://discord.com/careers",
    "slack":        "https://slack.com/careers",
    "dropbox":      "https://jobs.dropbox.com/",
    "spotify":      "https://www.lifeatspotify.com/jobs",
    "twitter":      "https://careers.twitter.com/en.html",
    "x":            "https://careers.x.com/en",
    "pinterest":    "https://www.pinterestcareers.com/",
    "snap":         "https://careers.snap.com/",
    "ramp":         "https://ramp.com/careers",
    "brex":         "https://www.brex.com/careers",
    "plaid":        "https://plaid.com/careers/",
    "databricks":   "https://www.databricks.com/company/careers",
    "snowflake":    "https://careers.snowflake.com/us/en",
    "palantir":     "https://www.palantir.com/careers/",
    "bytedance":    "https://jobs.bytedance.com/en/",
}


# ── Careers URL discovery ───────────────────────────────────────────────────────

def _find_careers_url(company_name: str) -> dict:
    """
    Given a company name, find their careers page URL.
    Strategy:
      1. Check known companies dict (instant, no network)
      2. Try <company>.com/careers and <company>.com/jobs directly
      3. Use DuckDuckGo search as final fallback
    Returns: { url, method, confidence }
    """
    slug = company_name.lower().strip().replace(" ", "").replace(".", "").replace(",", "")
    name_lower = company_name.lower().strip()

    # 1. Known companies
    for key, url in KNOWN_CAREERS.items():
        if key in name_lower or name_lower in key:
            return {"url": url, "method": "known_list", "confidence": "high"}

    # 2. Direct URL guesses — try common careers paths
    guesses = [
        f"https://www.{slug}.com/careers",
        f"https://www.{slug}.com/jobs",
        f"https://careers.{slug}.com",
        f"https://jobs.{slug}.com",
        f"https://{slug}.com/careers",
        f"https://{slug}.com/about/careers",
        f"https://{slug}.com/company/careers",
        f"https://www.{slug}.com/en/careers",
    ]
    for guess_url in guesses:
        try:
            r = req.get(guess_url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                # Quick sanity check: page should mention "jobs" or "careers"
                snippet = r.text[:5000].lower()
                if any(kw in snippet for kw in ["job", "career", "opening", "position", "role", "hiring"]):
                    return {"url": r.url, "method": "direct_guess", "confidence": "medium"}
        except Exception:
            continue

    # 3. DuckDuckGo search (no API key needed, uses HTML scraping)
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(company_name + ' careers jobs site')}"
    try:
        r = req.get(search_url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(r.text, "lxml")
        for result in soup.select(".result__url")[:8]:
            found_url = result.get_text(strip=True)
            if not found_url.startswith("http"):
                found_url = "https://" + found_url
            # Prefer URLs that contain career/job keywords
            if any(kw in found_url.lower() for kw in ["career", "job", "hiring", "work"]):
                return {"url": found_url, "method": "web_search", "confidence": "medium"}
        # If no keyword match, return the first result
        first = soup.select_one(".result__url")
        if first:
            found_url = first.get_text(strip=True)
            if not found_url.startswith("http"):
                found_url = "https://" + found_url
            return {"url": found_url, "method": "web_search", "confidence": "low"}
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")

    return {"url": None, "method": "none", "confidence": "none"}


# ── Page probing ────────────────────────────────────────────────────────────────

def _detect_ats(url: str, html: str) -> dict | None:
    for pattern, selectors in ATS_PATTERNS.items():
        if pattern in url or pattern in html[:3000]:
            return selectors
    return None


def _probe_page(url: str) -> dict:
    """Fetch the careers page and auto-detect job listing selectors."""
    needs_js = False
    html = ""
    jobs = []

    try:
        r = req.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return {"error": str(e), "needs_js": False, "selectors": _fallback_selectors(), "job_count": 0, "sample_jobs": []}

    soup = BeautifulSoup(html, "lxml")

    ats_selectors = _detect_ats(url, html)
    if ats_selectors:
        jobs = _test_selectors(soup, ats_selectors, url)
        if jobs:
            return {"needs_js": False, "selectors": ats_selectors, "job_count": len(jobs), "sample_jobs": jobs[:3]}

    js_signals = ["__NEXT_DATA__", "window.__NUXT__", "React.createElement", "ng-version", "data-reactroot", "__vue__"]
    needs_js = any(sig in html for sig in js_signals) or len(soup.find_all("a")) < 5

    selectors = _auto_detect_selectors(soup, url)
    jobs = _test_selectors(soup, selectors, url)

    if not jobs and needs_js:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=HEADERS["User-Agent"])
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2500)
                html = page.content()
                browser.close()

            soup = BeautifulSoup(html, "lxml")
            ats_selectors = _detect_ats(url, html)
            if ats_selectors:
                jobs = _test_selectors(soup, ats_selectors, url)
                if jobs:
                    return {"needs_js": True, "selectors": ats_selectors, "job_count": len(jobs), "sample_jobs": jobs[:3]}

            selectors = _auto_detect_selectors(soup, url)
            jobs = _test_selectors(soup, selectors, url)
        except Exception as e:
            logger.warning(f"Playwright probe failed: {e}")

    return {"needs_js": needs_js, "selectors": selectors, "job_count": len(jobs), "sample_jobs": jobs[:3]}


def _auto_detect_selectors(soup: BeautifulSoup, base_url: str) -> dict:
    job_patterns = ["/jobs/", "/careers/", "/job/", "/opening", "/position", "/role", "/vacancy", "/listing"]
    job_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(p in href.lower() for p in job_patterns) and href != base_url:
            text = a.get_text(strip=True)
            if 5 < len(text) < 150:
                job_links.append(a)

    if not job_links:
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            words = text.split()
            if 3 <= len(words) <= 8 and a.get("href", "").startswith("/"):
                job_links.append(a)

    if not job_links:
        return _fallback_selectors()

    container = _build_container_selector(job_links, base_url)
    return {
        "container": container,
        "title": "h3, h4, h2, .job-title, [class*='title'], p",
        "location": "[class*='location'], [class*='city'], span, p",
    }


def _build_container_selector(links: list, base_url: str) -> str:
    classes = [" ".join(a.get("class", [])) for a in links[:10]]
    if classes and len(set(classes)) == 1 and classes[0]:
        cls = classes[0].split()[0]
        return f"a.{cls}"
    hrefs = [a.get("href", "") for a in links[:10]]
    for pattern in ["/jobs/", "/careers/", "/job/", "/opening", "/position"]:
        if all(pattern in h for h in hrefs if h):
            return f"a[href*='{pattern}']"
    return "a[href*='/job'], a[href*='/career'], a[href*='/opening']"


def _test_selectors(soup: BeautifulSoup, selectors: dict, base_url: str) -> list:
    jobs = []
    seen = set()
    for el in soup.select(selectors.get("container", "a"))[:30]:
        link = el if el.name == "a" else el.find("a")
        url = link.get("href", "") if link else ""
        text = el.get_text(strip=True)[:100]
        if text and text not in seen and len(text) > 4:
            seen.add(text)
            jobs.append({"title": text, "url": url})
    return jobs


def _fallback_selectors() -> dict:
    return {
        "container": "a[href*='/job'], a[href*='/career'], a[href*='/opening']",
        "title": "h3, h4, h2, p",
        "location": "span, p",
    }


# ── Helpers ─────────────────────────────────────────────────────────────────────

def get_storage() -> JobStorage:
    cfg = load_config()
    return JobStorage(cfg["storage"]["db_path"])


# ── Routes ──────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    storage = get_storage()
    s = storage.get_stats()
    all_jobs = storage.get_recent_jobs(limit=10000)
    counts = {}
    for job in all_jobs:
        counts[job["company"]] = counts.get(job["company"], 0) + 1
    s["by_company"] = [{"company": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    return jsonify(s)


@app.route("/api/jobs")
def jobs():
    company  = request.args.get("company", "").strip().lower()
    location = request.args.get("location", "").strip().lower()
    search   = request.args.get("search", "").strip().lower()
    limit    = int(request.args.get("limit", 500))

    storage  = get_storage()
    all_jobs = storage.get_recent_jobs(limit=limit)

    if company:
        all_jobs = [j for j in all_jobs if j["company"].lower() == company]
    if location:
        all_jobs = [j for j in all_jobs if location in (j.get("location") or "").lower()]
    if search:
        all_jobs = [j for j in all_jobs
                    if search in (j.get("title") or "").lower()
                    or search in (j.get("company") or "").lower()
                    or search in (j.get("location") or "").lower()]

    return jsonify({"jobs": all_jobs, "total": len(all_jobs)})


@app.route("/api/locations")
def locations():
    """Return all distinct locations in the DB, sorted by frequency."""
    storage  = get_storage()
    all_jobs = storage.get_recent_jobs(limit=10000)
    counts = {}
    for job in all_jobs:
        loc = (job.get("location") or "").strip()
        if loc and loc.lower() not in ("not specified", "remote / not specified", ""):
            counts[loc] = counts.get(loc, 0) + 1
    sorted_locs = sorted(counts.items(), key=lambda x: -x[1])
    return jsonify([{"location": loc, "count": cnt} for loc, cnt in sorted_locs])


@app.route("/api/companies")
def companies():
    cfg = load_config()
    storage = get_storage()
    all_jobs = storage.get_recent_jobs(limit=10000)
    counts = {}
    for job in all_jobs:
        counts[job["company"]] = counts.get(job["company"], 0) + 1
    result = []
    for c in cfg["companies"]:
        result.append({
            "name": c["name"],
            "url": c["url"],
            "type": c.get("type", "static"),
            "job_count": counts.get(c["name"], 0),
        })
    return jsonify({"companies": result})


@app.route("/api/companies/search", methods=["POST"])
def search_company():
    """
    Main endpoint for the new UX:
    1. Take a company name
    2. Find their careers URL automatically
    3. Probe the page for job listings
    4. Return everything needed to confirm and save
    """
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Company name is required"}), 400

    logger.info(f"Searching for careers page: {name}")

    # Step 1: find the URL
    found = _find_careers_url(name)
    if not found["url"]:
        return jsonify({"error": f"Could not find a careers page for '{name}'. Try adding the URL manually."}), 404

    careers_url = found["url"]
    logger.info(f"Found careers URL via {found['method']}: {careers_url}")

    # Step 2: probe the page
    probe = _probe_page(careers_url)

    return jsonify({
        "name": name,
        "url": careers_url,
        "url_method": found["method"],       # how we found it
        "url_confidence": found["confidence"],
        "needs_js": probe.get("needs_js", True),
        "selectors": probe.get("selectors", _fallback_selectors()),
        "job_count": probe.get("job_count", 0),
        "sample_jobs": probe.get("sample_jobs", []),
        "error": probe.get("error"),
    })


@app.route("/api/companies/probe", methods=["POST"])
def probe_company():
    """Probe a specific URL directly (used when user overrides the detected URL)."""
    data = request.json or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not url.startswith("http"):
        url = "https://" + url
    result = _probe_page(url)
    result["url"] = url
    return jsonify(result)


@app.route("/api/companies/add", methods=["POST"])
def add_company():
    """Save a company to config.yaml and kick off an initial scrape."""
    data = request.json or {}
    name = (data.get("name") or "").strip()
    url  = (data.get("url")  or "").strip()
    if not name or not url:
        return jsonify({"error": "name and url are required"}), 400
    if not url.startswith("http"):
        url = "https://" + url

    scraper_type = data.get("type", "js")
    selectors = data.get("selectors") or _fallback_selectors()

    cfg = load_config()
    if any(c["name"].lower() == name.lower() for c in cfg["companies"]):
        return jsonify({"error": f"'{name}' is already being tracked"}), 409
    if any(c["url"] == url for c in cfg["companies"]):
        return jsonify({"error": "This URL is already tracked"}), 409

    new_entry = {"name": name, "url": url, "type": scraper_type, "selectors": selectors}
    cfg["companies"].append(new_entry)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info(f"Added company: {name} ({url})")

    def _scrape_new():
        try:
            from scrapers.generic import scraper_for
            from diff import find_new_jobs
            storage = get_storage()
            known_ids = storage.get_all_ids()
            scraper = scraper_for(new_entry)
            fresh = scraper.safe_fetch()
            new_jobs = find_new_jobs(fresh, known_ids)
            if new_jobs:
                storage.save_jobs(new_jobs)
            logger.info(f"Initial scrape for {name}: {len(new_jobs)} jobs found")
        except Exception as e:
            logger.error(f"Initial scrape failed for {name}: {e}")

    threading.Thread(target=_scrape_new, daemon=True).start()
    return jsonify({"status": "added", "company": new_entry})


@app.route("/api/companies/delete", methods=["POST"])
def delete_company():
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    cfg = load_config()
    before = len(cfg["companies"])
    cfg["companies"] = [c for c in cfg["companies"] if c["name"].lower() != name.lower()]
    if len(cfg["companies"]) == before:
        return jsonify({"error": f"Company '{name}' not found"}), 404
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    logger.info(f"Deleted company: {name}")
    return jsonify({"status": "deleted", "name": name})


@app.route("/api/config")
def get_config():
    cfg = load_config()
    return jsonify({
        "schedule": cfg["schedule"],
        "keywords_filter": cfg.get("keywords_filter", {}),
        "companies": [{"name": c["name"], "url": c["url"], "type": c.get("type", "static")} for c in cfg["companies"]],
    })


@app.route("/api/run", methods=["POST"])
def trigger_run():
    dry_run = (request.json or {}).get("dry_run", False)
    if not _check_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "A check is already running"}), 409
    def _run():
        try:
            new_jobs = run_check(load_config(), dry_run=dry_run)
            logger.info(f"Manual run complete: {len(new_jobs)} new jobs")
        finally:
            _check_lock.release()
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "dry_run": dry_run})


@app.route("/api/runs")
def run_history():
    import sqlite3
    cfg = load_config()
    conn = sqlite3.connect(cfg["storage"]["db_path"])
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])



@app.route("/api/jobs/<job_id>/status", methods=["POST"])
def set_job_status(job_id):
    """Set application status: none | saved | applied | rejected"""
    data   = request.json or {}
    status = (data.get("status") or "none").strip().lower()
    try:
        found = get_storage().set_status(job_id, status)
        if not found:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({"id": job_id, "status": status})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/jobs/by-status/<status>")
def jobs_by_status(status):
    jobs = get_storage().get_jobs_by_status(status)
    return jsonify({"jobs": jobs, "total": len(jobs)})


@app.route("/api/digest/send", methods=["POST"])
def trigger_digest():
    """Manually trigger a digest send from the dashboard."""
    from notifier import send_digest, send_whatsapp_digest
    cfg     = load_config()
    storage = get_storage()
    pending = storage.get_unnotified_jobs()

    if not pending:
        return jsonify({"status": "nothing_pending", "count": 0})

    label = (request.json or {}).get("label", "Manual Digest")
    sent  = send_digest(pending, cfg["email"], digest_label=label)

    if cfg.get("whatsapp"):
        try:
            send_whatsapp_digest(pending, cfg["whatsapp"], label=label)
        except Exception as e:
            logger.warning(f"WhatsApp digest failed: {e}")

    if sent:
        storage.mark_notified([j["id"] for j in pending])

    return jsonify({"status": "sent" if sent else "failed", "count": len(pending)})

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Job Alert API running at http://localhost:5000")
    app.run(debug=True, port=5000)
