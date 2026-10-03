"""What may be fetched and what robots.txt says: pure rules, no network."""

import pytest

from services.outreach_os import urlguard as g


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.fr/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pw@example.fr/",
        "https://example.fr:8443/",
        "http://example.fr:22/",
        "https:///nohost",
        "",
        "https://example.fr/" + "a" * 2100,
    ],
)
def test_urls_that_must_never_be_requested_are_refused(url):
    assert g.parse_target(url) is None


def test_a_plain_homepage_is_a_target_and_the_default_port_is_kept():
    t = g.parse_target("HTTPS://Example.FR./carte?x=1")
    assert (t.scheme, t.host, t.port, t.path) == ("https", "example.fr", 443, "/carte?x=1")
    assert t.url == "https://example.fr/carte?x=1" and t.origin == "https://example.fr"
    assert g.parse_target("http://example.fr").path == "/"


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "intranet",
        "printer.local",
        "db.internal",
        "facebook.com",
        "m.facebook.com",
        "www.linkedin.com",
        "x.com",
    ],
)
def test_internal_names_and_platforms_are_blocked(host):
    assert g.blocked_host(host) is True


def test_a_restaurants_own_domain_is_not_blocked():
    assert g.blocked_host("chez-marcel.fr") is False and g.blocked_host("linkedin.com.evil-resto.fr") is False


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
        "100.64.0.1",
        "not-an-ip",
    ],
)
def test_non_public_addresses_are_refused(ip):
    assert g.is_public_ip(ip) is False


def test_one_private_answer_among_public_ones_refuses_the_host():
    assert g.all_public(["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"]) is True
    assert g.all_public(["93.184.216.34", "10.0.0.1"]) is False
    assert g.all_public([]) is False


ROBOTS = "User-agent: *\nDisallow: /private\n\nUser-agent: BadBot\nDisallow: /\n"


def test_robots_rules_are_applied_to_our_agent():
    assert g.robots_decision(200, ROBOTS, "PlantiersOutreachOS/1.0", "https://x.fr/") is True
    assert g.robots_decision(200, ROBOTS, "PlantiersOutreachOS/1.0", "https://x.fr/private/a") is False
    assert g.robots_decision(200, "User-agent: *\nDisallow: /\n", "PlantiersOutreachOS/1.0", "https://x.fr/") is False


def test_a_missing_robots_file_allows_but_an_unreadable_one_forbids():
    assert g.robots_decision(404, None, "A", "https://x.fr/") is True
    assert g.robots_decision(410, None, "A", "https://x.fr/") is True
    for status in (None, 401, 403, 500, 503):
        assert g.robots_decision(status, None, "A", "https://x.fr/") is False
