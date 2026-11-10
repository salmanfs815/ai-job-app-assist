"""Who is making a request."""

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.usage import QuotaSubject, UsageKind

ADMIN_ROLE = "Admin"
INGEST_ROLE = "Postings.Ingest"


class PrincipalKind(StrEnum):
    USER = "user"
    GUEST = "guest"
    SERVICE = "service"


@dataclass(frozen=True, slots=True)
class Principal:
    kind: PrincipalKind
    # Users: identity-provider object ID. Guests: salted IP hash. Services: client app ID.
    id: str
    email: str | None = None
    display_name: str | None = None
    roles: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_user(self) -> bool:
        return self.kind is PrincipalKind.USER

    @property
    def is_guest(self) -> bool:
        return self.kind is PrincipalKind.GUEST

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @property
    def quota_subject(self) -> QuotaSubject:
        kind = UsageKind.USER if self.is_user else UsageKind.GUEST
        return QuotaSubject(owner_id=self.id, kind=kind)


def guest_principal(owner_id: str) -> Principal:
    return Principal(kind=PrincipalKind.GUEST, id=owner_id)
