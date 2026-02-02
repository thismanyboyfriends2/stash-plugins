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
    url: Optional[str] = None  # For internal use during scraping

    @classmethod
    def from_dict(cls, data: dict) -> 'Tag':
        """Create Tag from dictionary."""
        aliases = data.get('aliases', '')

        # Normalise aliases to list of strings
        if isinstance(aliases, str):
            aliases = [a.strip() for a in aliases.split(',') if a.strip()]
        elif isinstance(aliases, list):
            # Filter to strings only, strip whitespace
            aliases = [str(a).strip() for a in aliases if a and str(a).strip()]
        elif aliases is None:
            aliases = []
        else:
            # Invalid type, treat as empty
            aliases = []

        return cls(
            name=data['name'],
            description=data.get('description', ''),
            stash_id=data.get('stash_id', ''),
            url=data.get('url'),
            aliases=aliases,
            category=data.get('category')
        )


@dataclass
class StashConnection:
    """Configuration for connecting to a local Stash instance via GraphQL."""
    scheme: str = "http"
    host: str = "localhost"
    port: int = 9999
    api_key: Optional[str] = None

    def to_connection_dict(self) -> dict:
        """Convert to connection dictionary."""
        conn = {
            "Scheme": self.scheme,
            "Host": self.host,
            "Port": self.port,
        }
        if self.api_key:
            conn["ApiKey"] = self.api_key
        return conn



@dataclass
class Config:
    """Configuration for the stash tag scraper."""
    stashdb_api_key: str
    ignored_aliases: list[str] = None  # Aliases to skip during merge

    def __post_init__(self):
        """Initialise ignored_aliases if not provided."""
        if self.ignored_aliases is None:
            self.ignored_aliases = []

