import pytest

from app.core.network import client_ip, client_ip_from_scope


@pytest.mark.parametrize(
    ("peer", "forwarded", "hops", "expected"),
    [
        ("10.0.0.1", [], 1, "10.0.0.1"),  # no proxy header: use the socket peer
        ("10.0.0.1", ["203.0.113.7"], 1, "203.0.113.7"),
        # The client prepended a forged entry; only the one our proxy appended counts.
        ("10.0.0.1", ["1.2.3.4, 203.0.113.7"], 1, "203.0.113.7"),
        ("10.0.0.1", ["1.2.3.4", "203.0.113.7"], 1, "203.0.113.7"),
        ("10.0.0.1", ["203.0.113.7, 10.0.0.9"], 2, "203.0.113.7"),
        ("10.0.0.1", ["203.0.113.7"], 5, "203.0.113.7"),  # fewer entries than hops
        ("10.0.0.1", ["203.0.113.7"], 0, "10.0.0.1"),  # header ignored entirely
        ("10.0.0.1", ["203.0.113.7:51234"], 1, "203.0.113.7"),
        ("10.0.0.1", ["[2001:db8::1]:443"], 1, "2001:db8::1"),
        ("10.0.0.1", ["2001:db8::1"], 1, "2001:db8::1"),
        (None, [], 1, "unknown"),
        ("10.0.0.1", [" , "], 1, "10.0.0.1"),
    ],
)
def test_client_ip(peer: str | None, forwarded: list[str], hops: int, expected: str) -> None:
    assert client_ip(peer, forwarded, hops) == expected


def test_client_ip_from_scope_reads_headers_case_insensitively() -> None:
    scope = {
        "type": "http",
        "client": ("10.0.0.1", 1234),
        "headers": [(b"X-Forwarded-For", b"203.0.113.7")],
    }

    assert client_ip_from_scope(scope, 1) == "203.0.113.7"
    assert client_ip_from_scope({"type": "http", "headers": []}, 1) == "unknown"
