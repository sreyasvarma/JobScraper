"""
Base scraper class that all company scrapers inherit from.
Each company scraper only needs to implement fetch_jobs().
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import logging

logger = logging.getLogger(__name__)


@dataclass
class Job:
    title: str
    url: str
    company: str
    location: str = "Not specified"
    department: str = ""

    @property
    def id(self) -> str:
        """Unique fingerprint for this job — used to detect duplicates."""
        raw = f"{self.company}::{self.url or self.title}"
        return hashlib.md5(raw.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "company": self.company,
            "location": self.location,
            "department": self.department,
        }

    def __repr__(self):
        return f"<Job [{self.company}] {self.title} @ {self.location}>"


class BaseScraper(ABC):
    company: str = ""
    url: str = ""

    @abstractmethod
    def fetch_jobs(self) -> list[Job]:
        """Scrape the careers page and return a list of Job objects."""
        raise NotImplementedError

    def safe_fetch(self) -> list[Job]:
        """Wrapper that catches errors so one bad scraper doesn't break the run."""
        try:
            jobs = self.fetch_jobs()
            logger.info(f"[{self.company}] Found {len(jobs)} jobs")
            return jobs
        except Exception as e:
            logger.error(f"[{self.company}] Scraper failed: {e}", exc_info=True)
            return []
