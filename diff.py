"""
Diff engine: compares freshly scraped jobs against what's stored.
Returns only jobs that are genuinely new.
"""

import logging
from scrapers.base import Job

logger = logging.getLogger(__name__)


def find_new_jobs(
    fresh_jobs: list[Job],
    known_ids: set[str],
    keywords_config: dict | None = None,
) -> list[Job]:
    """
    Return jobs from fresh_jobs that are not in known_ids.
    Optionally filters by keyword inclusion/exclusion lists.
    """
    new_jobs = [j for j in fresh_jobs if j.id not in known_ids]
    # ASCII-safe log message (no Unicode arrows) for Windows cp1252 terminals
    logger.info(f"Diff: {len(fresh_jobs)} scraped, {len(new_jobs)} new")

    if keywords_config:
        new_jobs = _apply_keyword_filter(new_jobs, keywords_config)

    return new_jobs


def _apply_keyword_filter(jobs: list[Job], config: dict) -> list[Job]:
    include = [kw.lower() for kw in config.get("include", [])]
    exclude = [kw.lower() for kw in config.get("exclude", [])]

    filtered = []
    for job in jobs:
        text = f"{job.title} {job.department}".lower()

        if include and not any(kw in text for kw in include):
            continue

        if any(kw in text for kw in exclude):
            logger.debug(f"Excluded by keyword filter: {job.title}")
            continue

        filtered.append(job)

    logger.info(f"Keyword filter: {len(jobs)} in, {len(filtered)} out")
    return filtered
