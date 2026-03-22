from .base import BaseScraper, Job
from .generic import GenericStaticScraper, GenericJSScraper, scraper_for
from .apple import AppleScraper
from .nvidia import NvidiaScraper
from .rippling import RipplingScraper
from .meta import MetaScraper

__all__ = [
    "BaseScraper", "Job",
    "GenericStaticScraper", "GenericJSScraper", "scraper_for",
    "AppleScraper", "NvidiaScraper", "RipplingScraper", "MetaScraper",
]
