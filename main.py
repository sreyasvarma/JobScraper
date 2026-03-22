"""
Main orchestrator: scrapes jobs, saves to DB, sends digests at 9am and 6pm.
Run continuously: python main.py
Run once:         python main.py --once
Test (no alerts): python main.py --dry-run
"""

import yaml
import logging
import argparse
import time
import sys
from datetime import datetime

from scrapers.generic import scraper_for
from storage import JobStorage
from diff import find_new_jobs
from notifier import send_digest, send_whatsapp_digest, send_alert

# ── Logging ────────────────────────────────────────────────────────────────────

def setup_logging(log_path: str):
    fmt    = "%(asctime)s  %(levelname)-8s  %(name)s - %(message)s"
    stream = logging.StreamHandler(sys.stdout)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    stream.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    logging.basicConfig(level=logging.INFO, handlers=[stream, fh])

logger = logging.getLogger(__name__)


# ── Config ─────────────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Keyword filtering for DevOps / Cloud / AI/ML ──────────────────────────────

ROLE_GROUPS = {
    "devops": [
        "devops", "dev ops", "sre", "site reliability", "platform engineer",
        "infrastructure", "infra", "ci/cd", "cicd", "kubernetes", "k8s",
        "docker", "terraform", "ansible", "helm", "jenkins", "gitlab",
        "pipeline", "devsecops", "cloud engineer", "cloud ops",
    ],
    "cloud": [
        "cloud", "aws", "azure", "gcp", "google cloud", "amazon web services",
        "solutions architect", "cloud architect", "cloud native",
    ],
    "ai_ml": [
        "machine learning", "ml engineer", "ai engineer", "data scientist",
        "deep learning", "nlp", "llm", "computer vision", "mlops",
        "research scientist", "research engineer", "applied scientist",
        "artificial intelligence", "generative ai", "gen ai", "foundation model",
        "reinforcement learning", "data engineer",
    ],
}

def _matches_role_filter(job, role_keywords: list[str]) -> bool:
    if not role_keywords:
        return True
    text = f"{job.title} {job.department}".lower()
    return any(kw in text for kw in role_keywords)


# ── Scrape cycle ───────────────────────────────────────────────────────────────

def run_check(config: dict, dry_run: bool = False) -> list:
    logger.info("=" * 60)
    logger.info(f"Starting job check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    storage   = JobStorage(config["storage"]["db_path"])
    known_ids = storage.get_all_ids()
    logger.info(f"Known jobs in DB: {len(known_ids)}")

    all_new_jobs = []

    for company_cfg in config["companies"]:
        scraper   = scraper_for(company_cfg)
        fresh     = scraper.safe_fetch()
        new_jobs  = find_new_jobs(fresh, known_ids, keywords_config=config.get("keywords_filter"))
        all_new_jobs.extend(new_jobs)
        for j in new_jobs:
            known_ids.add(j.id)

    logger.info(f"Total new jobs found: {len(all_new_jobs)}")

    if all_new_jobs:
        storage.save_jobs(all_new_jobs)
        if dry_run:
            logger.info("[DRY RUN] Jobs found (no notifications sent):")
            for j in all_new_jobs:
                logger.info(f"  [{j.company}] {j.title} - {j.location or 'N/A'}")

    storage.log_run(companies_checked=len(config["companies"]), new_jobs=len(all_new_jobs))
    logger.info(f"DB stats: {storage.get_stats()}")
    logger.info("Check complete.")
    return all_new_jobs


# ── Digest sender ──────────────────────────────────────────────────────────────

def send_pending_digest(config: dict, label: str):
    """Send digest of all unnotified jobs, then mark them as notified."""
    storage    = JobStorage(config["storage"]["db_path"])
    pending    = storage.get_unnotified_jobs()

    if not pending:
        logger.info(f"Digest [{label}]: no pending jobs to send")
        return

    logger.info(f"Digest [{label}]: sending {len(pending)} jobs")
    sent = False

    # Email digest
    try:
        sent = send_digest(pending, config["email"], digest_label=label)
    except Exception as e:
        logger.error(f"Email digest failed: {e}")

    # WhatsApp digest
    if config.get("whatsapp"):
        try:
            send_whatsapp_digest(pending, config["whatsapp"], label=label)
        except Exception as e:
            logger.error(f"WhatsApp digest failed: {e}")

    # Mark as notified so they don't appear in the next digest
    if sent:
        storage.mark_notified([j["id"] for j in pending])
        logger.info(f"Marked {len(pending)} jobs as notified")


# ── Scheduler ──────────────────────────────────────────────────────────────────

def run_scheduler(config: dict):
    """
    Runs continuously:
    - Scrapes every `interval_hours` hours
    - Sends digest at 09:00 and 18:00 (configurable)
    """
    interval_hours  = config["schedule"]["interval_hours"]
    interval_secs   = interval_hours * 3600
    digest_times    = config["schedule"].get("digest_times", ["09:00", "18:00"])

    logger.info(f"Scheduler started - scrape every {interval_hours}h, digests at {digest_times}")

    last_digest_sent = {}   # tracks which digest times we've already sent today
    last_scrape      = 0.0

    while True:
        now      = datetime.now()
        hhmm     = now.strftime("%H:%M")
        date_str = now.strftime("%Y-%m-%d")

        # Scrape check
        if time.time() - last_scrape >= interval_secs:
            run_check(config)
            last_scrape = time.time()

        # Digest check — send if we're within 1 minute of a scheduled time
        for digest_time in digest_times:
            key = f"{date_str}_{digest_time}"
            if key not in last_digest_sent:
                dh, dm = map(int, digest_time.split(":"))
                diff   = abs(now.hour * 60 + now.minute - dh * 60 - dm)
                if diff <= 1:
                    label = "Morning Digest" if dh < 12 else "Evening Digest"
                    send_pending_digest(config, label=label)
                    last_digest_sent[key] = True

        time.sleep(60)  # check every minute for digest timing accuracy


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Job Alert Scraper")
    parser.add_argument("--config",      default="config.yaml")
    parser.add_argument("--once",        action="store_true", help="Scrape once and exit")
    parser.add_argument("--dry-run",     action="store_true", help="Scrape but skip all notifications")
    parser.add_argument("--send-digest", action="store_true", help="Send pending digest now and exit")
    args   = parser.parse_args()
    config = load_config(args.config)
    setup_logging(config["storage"]["log_path"])

    if args.dry_run:
        run_check(config, dry_run=True)
    elif args.send_digest:
        send_pending_digest(config, label="Manual Digest")
    elif args.once:
        run_check(config)
    else:
        run_scheduler(config)


if __name__ == "__main__":
    main()
