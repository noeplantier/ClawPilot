"""The polite homepage fetcher with a fake DNS and a fake transport: no socket is ever opened."""

import pytest

from services import site_fetcher_svc as sf

PUBLIC = ["93.184.216.34"]


class World:
    """Scripted answers per (host, path); records every request so politeness can be asserted."""

    def __init__(self, pages, ips=None):
        self.pages, self.ips, self.requests, self.slept, self.now = pages, ips or {}, [], [], 0.0

    def resolver(self, host):
        answer = self.ips.get(host, PUBLIC)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def transport(self, target, ip, headers):
        self.requests.append((target.host, target.path, ip, headers))
        answer = self.pages.get((target.host, target.path), sf.RawResponse(404, {}, b""))
        if isinstance(answer, Exception):
            raise answer
        return answer

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds

    def clock(self):
        return self.now

    def fetcher(self):
        return sf.HttpSiteFetcher(resolver=self.resolver, transport=self.transport, sleep=self.sleep, clock=self.clock)


def html(body="<html><body>Bonjour</body></html>", status=200, **headers):
    return sf.RawResponse(status, {"content-type": "text/html; charset=utf-8", **headers}, body.encode())


ROBOTS_OK = sf.RawResponse(200, {}, b"User-agent: *\nDisallow: /admin\n")


def test_an_allowed_homepage_is_fetched_with_an_identified_agent_and_the_validated_ip():
    w = World({("chez-marcel.fr", "/robots.txt"): ROBOTS_OK, ("chez-marcel.fr", "/"): html()})
    snap = w.fetcher().fetch("https://chez-marcel.fr/")
    assert snap.status == 200 and "Bonjour" in snap.html
    assert [r[1] for r in w.requests] == ["/robots.txt", "/"]
    assert all(r[2] == PUBLIC[0] for r in w.requests)  # connected to the address that was checked
    assert all(r[3]["User-Agent"].startswith("PlantiersOutreachOS/1.0") for r in w.requests)


def test_robots_txt_that_forbids_means_not_checked_and_the_page_is_never_requested():
    w = World(
        {("a.fr", "/robots.txt"): sf.RawResponse(200, {}, b"User-agent: *\nDisallow: /\n"), ("a.fr", "/"): html()}
    )
    assert w.fetcher().fetch("https://a.fr/") is None
    assert [r[1] for r in w.requests] == ["/robots.txt"]


def test_an_unreadable_robots_txt_is_not_permission():
    w = World({("a.fr", "/robots.txt"): sf.RawResponse(503, {}, b""), ("a.fr", "/"): html()})
    assert w.fetcher().fetch("https://a.fr/") is None
    w = World({("a.fr", "/robots.txt"): sf.TransportError("other"), ("a.fr", "/"): html()})
    assert w.fetcher().fetch("https://a.fr/") is None


def test_a_missing_robots_txt_allows():
    w = World({("a.fr", "/"): html()})  # robots.txt -> 404 by default
    assert w.fetcher().fetch("https://a.fr/").status == 200


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_access_refused_or_throttled_concludes_nothing_and_is_not_retried(status):
    w = World({("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): sf.RawResponse(status, {}, b"captcha")})
    assert w.fetcher().fetch("https://a.fr/") is None
    assert [r[1] for r in w.requests].count("/") == 1


def test_a_real_404_is_reported_but_a_timeout_is_not():
    w = World({("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): sf.RawResponse(404, {}, b"")})
    snap = w.fetcher().fetch("https://a.fr/")
    assert (snap.status, snap.html) == (404, None)
    w = World({("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): sf.TransportError("other")})
    assert w.fetcher().fetch("https://a.fr/") is None


def test_a_host_name_that_does_not_exist_is_reported_but_a_dns_hiccup_is_not():
    snap = World({}, {"gone.fr": sf.TransportError("dns")}).fetcher().fetch("https://gone.fr/")
    assert snap.status is None and "does not resolve" in snap.error
    assert World({}, {"slow.fr": sf.TransportError("other")}).fetcher().fetch("https://slow.fr/") is None


@pytest.mark.parametrize("ips", [["10.0.0.1"], ["127.0.0.1"], ["169.254.169.254"], ["93.184.216.34", "192.168.0.9"]])
def test_a_host_resolving_to_a_non_public_address_is_never_contacted(ips):
    w = World({("evil.fr", "/robots.txt"): ROBOTS_OK, ("evil.fr", "/"): html()}, {"evil.fr": ips})
    assert w.fetcher().fetch("https://evil.fr/") is None and w.requests == []


@pytest.mark.parametrize(
    "url", ["https://www.linkedin.com/company/x", "http://localhost/", "ftp://a.fr/", "https://m.facebook.com/x"]
)
def test_platforms_internal_names_and_odd_schemes_are_never_requested(url):
    w = World({})
    assert w.fetcher().fetch(url) is None and w.requests == []


def test_a_redirect_to_a_private_host_or_a_platform_is_not_followed():
    for location in ("http://10.0.0.1/admin", "https://www.facebook.com/page"):
        w = World(
            {("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): sf.RawResponse(302, {"location": location}, b"")},
            {"10.0.0.1": ["10.0.0.1"]},
        )
        assert w.fetcher().fetch("https://a.fr/") is None
        assert all(r[0] == "a.fr" for r in w.requests)


def test_a_redirect_to_the_same_site_is_followed_and_robots_is_checked_for_the_new_host():
    w = World(
        {
            ("a.fr", "/robots.txt"): ROBOTS_OK,
            ("a.fr", "/"): sf.RawResponse(301, {"location": "https://www.a.fr/"}, b""),
            ("www.a.fr", "/robots.txt"): sf.RawResponse(200, {}, b"User-agent: *\nDisallow: /\n"),
            ("www.a.fr", "/"): html(),
        }
    )
    assert w.fetcher().fetch("https://a.fr/") is None  # the new host's robots.txt forbids
    assert ("www.a.fr", "/robots.txt") in [(r[0], r[1]) for r in w.requests]


def test_redirect_loops_stop():
    w = World(
        {("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): sf.RawResponse(302, {"location": "https://a.fr/"}, b"")}
    )
    assert w.fetcher().fetch("https://a.fr/") is None
    assert [r[1] for r in w.requests].count("/") <= sf.MAX_REDIRECTS + 1


def test_non_html_and_oversized_answers_are_not_checked():
    pdf = sf.RawResponse(200, {"content-type": "application/pdf"}, b"%PDF")
    assert World({("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): pdf}).fetcher().fetch("https://a.fr/") is None
    big = sf.RawResponse(200, {"content-type": "text/html"}, b"x" * (sf.MAX_BYTES + 1))
    assert World({("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): big}).fetcher().fetch("https://a.fr/") is None


def test_requests_to_the_same_host_are_spaced_out():
    w = World({("a.fr", "/robots.txt"): ROBOTS_OK, ("a.fr", "/"): html()})
    w.fetcher().fetch("https://a.fr/")
    assert w.slept and w.slept[0] >= 0 and sum(w.slept) >= sf.MIN_DELAY_SECONDS - 0.001  # robots.txt then the page


def test_the_run_budget_is_respected_and_the_rest_is_not_checked():
    pages = {}
    for i in range(sf.MAX_FETCHES + 5):
        pages[(f"s{i}.fr", "/")] = html()
    w = World(pages)
    f = w.fetcher()
    results = [f.fetch(f"https://s{i}.fr/") for i in range(sf.MAX_FETCHES + 5)]
    assert sum(r is not None for r in results) == sf.MAX_FETCHES
    assert all(r is None for r in results[sf.MAX_FETCHES :])
    late = World({("a.fr", "/"): html()})
    f2 = late.fetcher()
    late.now = sf.DEADLINE_SECONDS + 1
    assert f2.fetch("https://a.fr/") is None
