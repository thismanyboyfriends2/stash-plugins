"""Data models for the stash tag scraper."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Tag:
    """Represents a tag from StashDB."""
    name: str
    description: str
    stash_id: str
    aliases: list[str]
    category: Optional[str] = None


@dataclass
class Config:
    """Configuration for the stash tag scraper."""
    stashdb_api_key: str
    ignored_aliases: list[str] = None  # Aliases to skip during merge

    def __post_init__(self):
        """Initialise ignored_aliases if not provided."""
        if self.ignored_aliases is None:
            self.ignored_aliases = []

