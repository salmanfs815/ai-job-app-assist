"""Client IP resolution behind a reverse proxy."""

from collections.abc import Iterable

from starlette.types import Scope

UNKNOWN_CLIENT = "unknown"


def client_ip(peer: str | None, forwarded_for: Iterable[str], trusted_proxy_hops: int) -> str:
    """Return the address of the client as seen by the outermost *trusted* proxy.

    Each proxy appends the address it received the request from to
    ``X-Forwarded-For``. Anything left of the entries added by our own proxies is
    supplied by the client and cannot be trusted, so with ``n`` trusted hops the
    client address is the ``n``-th entry from the right.
    """
    if trusted_proxy_hops > 0:
        entries = [part.strip() for value in forwarded_for for part in value.split(",") if part.strip()]
        if entries:
            index = max(len(entries) - trusted_proxy_hops, 0)
            return _strip_port(entries[index])
    return peer or UNKNOWN_CLIENT


def client_ip_from_scope(scope: Scope, trusted_proxy_hops: int) -> str:
    client = scope.get("client")
    peer = client[0] if client else None
    forwarded = [
        value.decode("latin-1") for name, value in scope.get("headers", []) if name.lower() == b"x-forwarded-for"
    ]
    return client_ip(peer, forwarded, trusted_proxy_hops)


def _strip_port(address: str) -> str:
    if address.startswith("["):  # [IPv6]:port
        return address[1:].split("]", 1)[0]
    if address.count(":") == 1:  # IPv4:port
        return address.split(":", 1)[0]
    return address
