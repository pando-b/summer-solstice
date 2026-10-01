"""Name and slug availability (R6, AE4, KTD7). Every response replayed here is
a hand-built synthetic fixture; no test touches the network. A lookup that
cannot answer is `pending`, never `available`."""

import json
from pathlib import Path

import pytest

from solstice import namecheck
from solstice.__main__ import main
from solstice.adapters.base import Request, Response, TransportError

FIX = Path(__file__).parent / "fixtures" / "namecheck"


def fixture(name: str) -> Response:
    data = json.loads((FIX / name).read_text())
    return Response(status=data["status"], headers=data["headers"],
                    body=json.dumps(data["body"]).encode())


class FakeTransport:
    def __init__(self, *responses):
        self.queue = list(responses)
        self.requests: list[Request] = []

    def __call__(self, req: Request) -> Response:
        self.requests.append(req)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def deps(*responses, clock=None):
    from factories import Clock

    t = FakeTransport(*responses)
    return namecheck.Deps(transport=t, now=clock or Clock()), t


# --- WordPress.org ----------------------------------------------------------


def test_wporg_slug_found_is_taken():  # AE4
    d, t = deps(fixture("wporg_plugin_found.json"))
    r = namecheck.check_wporg("example-restock-alerts", d)
    assert r["status"] == "taken"
    assert r["check"] == "wporg" and r["name"] == "example-restock-alerts"
    assert "action=plugin_information" in t.requests[0].url
    assert "example-restock-alerts" in t.requests[0].url
    assert r["checked_at"] == "2026-01-05T12:00:00Z"


def test_wporg_not_found_is_available():
    d, _ = deps(fixture("wporg_plugin_not_found.json"))
    assert namecheck.check_wporg("example-free-slug", d)["status"] == "available"


def test_wporg_closed_slug_stays_taken():
    d, _ = deps(fixture("wporg_plugin_closed.json"))
    r = namecheck.check_wporg("example-closed-plugin", d)
    assert r["status"] == "taken"
    assert "closed" in r["detail"]


@pytest.mark.parametrize("outcome", [
    TransportError("TimeoutError: timed out"),
    Response(503, {}, b"{}"),
    Response(429, {"Retry-After": "30"}, b"{}"),
    Response(200, {}, b"<html>not json</html>"),
    Response(200, {}, b'{"unexpected": true}'),
])
def test_wporg_lookup_that_cannot_answer_is_pending(outcome):
    d, _ = deps(outcome)
    r = namecheck.check_wporg("example-free-slug", d)
    assert r["status"] == "pending"
    assert r["detail"]


@pytest.mark.parametrize("bad", ["Example Slug", "", "slug/../x", "-lead", "x" * 201])
def test_wporg_bad_slug_is_a_usage_error(bad):
    d, t = deps()
    with pytest.raises(namecheck.UsageError):
        namecheck.check_wporg(bad, d)
    assert t.requests == []


# --- domains through RDAP ------------------------------------------------------


def test_domain_registered_is_taken():
    d, t = deps(fixture("rdap_bootstrap_redirect.json"), fixture("rdap_domain_found.json"))
    r = namecheck.check_domain("example-restock.com", d)
    assert r["status"] == "taken"
    assert t.requests[0].url == "https://rdap.org/domain/example-restock.com"
    assert t.requests[1].url == "https://rdap.registry.example/domain/example-restock.com"


def test_domain_registry_not_found_is_available():
    d, _ = deps(fixture("rdap_bootstrap_redirect.json"), fixture("rdap_domain_not_found.json"))
    r = namecheck.check_domain("example-restock.com", d)
    assert r["status"] == "available"
    assert "registry" in r["detail"]


def test_domain_with_no_rdap_service_is_pending_not_available():
    # rdap.org answers 404 itself (no redirect) when it knows no RDAP server
    # for the TLD: that says nothing about the name.
    d, _ = deps(fixture("rdap_no_service.json"))
    r = namecheck.check_domain("example-restock.zz", d)
    assert r["status"] == "pending"


@pytest.mark.parametrize("second", [
    TransportError("TimeoutError: timed out"),
    Response(500, {}, b"{}"),
    Response(429, {}, b"{}"),
])
def test_domain_registry_failure_is_pending(second):
    d, _ = deps(fixture("rdap_bootstrap_redirect.json"), second)
    assert namecheck.check_domain("example-restock.com", d)["status"] == "pending"


def test_domain_redirect_loop_is_pending():
    loop = Response(302, {"Location": "https://rdap.registry.example/domain/example-restock.com"}, b"")
    d, t = deps(*([loop] * 10))
    assert namecheck.check_domain("example-restock.com", d)["status"] == "pending"
    assert len(t.requests) <= namecheck.MAX_REDIRECTS + 1


def test_domain_redirect_to_plain_http_is_pending():
    d, t = deps(Response(302, {"Location": "http://rdap.registry.example/domain/x.com"}, b""))
    assert namecheck.check_domain("example-restock.com", d)["status"] == "pending"
    assert len(t.requests) == 1


@pytest.mark.parametrize("bad", ["nodot", "has space.com", "https://example.com", "-x.com", ""])
def test_bad_domain_is_a_usage_error(bad):
    d, t = deps()
    with pytest.raises(namecheck.UsageError):
        namecheck.check_domain(bad, d)
    assert t.requests == []


# --- CLI ----------------------------------------------------------------------


def test_cli_prints_availability_json(monkeypatch, capsys):
    d, _ = deps(fixture("wporg_plugin_found.json"))
    monkeypatch.setattr(namecheck, "Deps", lambda: d)
    assert main(["namecheck", "--wporg", "example-restock-alerts"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "taken" and out["check"] == "wporg"


def test_cli_timeout_prints_pending_and_exits_zero(monkeypatch, capsys):
    d, _ = deps(TransportError("TimeoutError: timed out"))
    monkeypatch.setattr(namecheck, "Deps", lambda: d)
    assert main(["namecheck", "--domain", "example-restock.com"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pending"


@pytest.mark.parametrize("argv", [["namecheck"],
                                  ["namecheck", "--wporg", "a-slug", "--domain", "a.com"]])
def test_cli_needs_exactly_one_target(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 64
    assert json.loads(capsys.readouterr().err)["error"]["kind"] == "usage"


def test_cli_bad_slug_prints_the_usage_envelope(capsys):
    assert main(["namecheck", "--wporg", "Not A Slug"]) == 64
    assert json.loads(capsys.readouterr().err)["error"]["kind"] == "usage"
