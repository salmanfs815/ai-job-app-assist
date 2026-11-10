"""User accounts."""

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True, slots=True)
class User:
    """Created the first time a person signs in. ``id`` is the identity provider's object ID."""

    id: str
    created_at: datetime
    last_seen_at: datetime
    email: str | None = None
    display_name: str | None = None

    def seen(self, now: datetime, *, email: str | None, display_name: str | None) -> "User":
        """Refresh the last-seen time and pick up profile changes from the latest token."""
        return replace(
            self,
            last_seen_at=now,
            email=email or self.email,
            display_name=display_name or self.display_name,
        )
