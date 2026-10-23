"""A business's public contact on its OWN site: homepage first, then its contact page. Offline, fixtures only."""

import asyncio

import pytest

from services.outreach_os import contact, pipeline
from services.outreach_os.types import SiteSnapshot

SITE = "https://www.petit-bouchon.example"
HOME_WITH_LINK = '<nav><a href="/menu">Menu</a><a class="c" href="/fr/nous-contacter?utm=x#form">Contact</a></nav>'
CONTACT_PAGE = (
    '<p>Écrivez-nous : <a href="mailto:resa@petit-bouchon.example?subject=hello">resa@petit-bouchon.example</a></p>'
)


@pytest.mark.parametrize(
    "href,expected",
    [
        ("/contact", f"{SITE}/contact"),
        ("contact.html", f"{SITE}/contact.html"),
        ("/fr/nous-contacter?utm=x#form", f"{SITE}/fr/nous-contacter?utm=x"),
        ("https://petit-bouchon.example/contactez-nous/", "https://petit-bouchon.example/contactez-nous/"),
        ("/en/contact-us", f"{SITE}/en/contact-us"),
        ("/kontakt", f"{SITE}/kontakt"),
    ],
)
def test_a_contact_link_of_the_same_site_is_found(href, expected):
    assert contact.find_contact_page(f'<a href="{href}">x</a>', SITE) == expected


@pytest.mark.parametrize(
    "html",
    [
        '<a href="https://another-site.example/contact">other site</a>',  # never another site
        '<a href="mailto:contact@petit-bouchon.example">mail</a>',  # not a page
        '<a href="tel:+33478000000">tel</a>',
        '<a href="javascript:void(0)">js</a>',
        '<a href="/menu">menu</a><a href="/contact-form-builder">other</a>',  # only an exact contact word
        '<a href="ftp://petit-bouchon.example/contact">ftp</a>',
        "",
        None,
    ],
)
def test_nothing_else_is_followed(html):
    assert contact.find_contact_page(html, SITE) is None


def test_without_a_site_nothing_is_found():
    assert contact.find_contact_page(HOME_WITH_LINK, None) is None


class Fetcher:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def fetch(self, url):
        self.asked.append(url)
        html = self.pages.get(url)
        return None if html is None else SiteSnapshot(url, 200, html)


def run(fetcher, home_html):
    return asyncio.run(pipeline.site_contact_email(fetcher, SiteSnapshot(SITE, 200, home_html), SITE))


def test_the_homepage_wins_and_costs_no_second_request():
    fetcher = Fetcher({})
    assert run(fetcher, '<a href="mailto:contact@petit-bouchon.example">x</a>') == (
        "contact@petit-bouchon.example",
        "homepage",
    )
    assert fetcher.asked == []


def test_the_contact_page_is_read_when_the_homepage_publishes_no_address():
    fetcher = Fetcher({f"{SITE}/fr/nous-contacter?utm=x": CONTACT_PAGE})
    assert run(fetcher, HOME_WITH_LINK) == ("resa@petit-bouchon.example", "contact page")
    assert fetcher.asked == [f"{SITE}/fr/nous-contacter?utm=x"]  # exactly one extra page, the one the site links to


def test_a_blocked_or_empty_contact_page_gives_nothing_and_is_not_guessed():
    assert run(Fetcher({}), HOME_WITH_LINK) == (None, None)  # robots.txt / unreachable: the fetcher answers None
    nothing = Fetcher({f"{SITE}/fr/nous-contacter?utm=x": "<p>Formulaire uniquement</p>"})
    assert run(nothing, HOME_WITH_LINK) == (None, None)


def test_an_address_of_another_domain_on_the_contact_page_is_ignored():
    page = '<a href="mailto:someone@gmail.com">x</a>'
    assert run(Fetcher({f"{SITE}/fr/nous-contacter?utm=x": page}), HOME_WITH_LINK) == (None, None)


def test_no_link_means_no_second_request():
    fetcher = Fetcher({})
    assert run(fetcher, '<a href="/menu">Menu</a>') == (None, None)
    assert fetcher.asked == []
