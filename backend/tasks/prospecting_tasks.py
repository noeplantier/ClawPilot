"""Asynchronous free-source discovery and public website enrichment."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import re
import socket
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp.abc import AbstractResolver
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from celery_app import celery_app
from db.models import Contact, DiscoveryJob, DiscoveredPlace, EnrichmentJob, Lead, PublicPageCache

logger = logging.getLogger("clawpilot.prospecting")
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
QUERY_VERSION = "v1"
CATEGORIES = {
    "restaurant": 'amenity="restaurant"',
    "cafe": 'amenity="cafe"',
    "hotel": 'tourism="hotel"',
    "shop": "shop",
    "office": "office",
    "beauty": 'shop="beauty"',
    "dentist": 'healthcare="dentist"',
    "company": 'office="company"',
}


def _key(bbox: list[float], category: str) -> str:
    normalized = [round(value, 4) for value in bbox]
    return hashlib.sha256(f"{normalized}|{category}|{QUERY_VERSION}".encode()).hexdigest()


def _overpass_query(bbox: list[float], category: str) -> str:
    south, west, north, east = bbox
    selector = CATEGORIES[category]
    return (
        f"[out:json][timeout:25];(node[{selector}]({south},{west},{north},{east});"
        f"way[{selector}]({south},{west},{north},{east});"
        f"relation[{selector}]({south},{west},{north},{east}););out center tags 500;"
    )


async def _fetch_overpass(bbox: list[float], category: str) -> list[dict]:
    timeout = aiohttp.ClientTimeout(total=35, connect=8)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={"User-Agent": "Plantiers-OutreachOS/1.0 (public OSM discovery)"},
    ) as session:
        for endpoint in ENDPOINTS:
            for attempt in range(2):
                try:
                    async with session.post(endpoint, data={"data": _overpass_query(bbox, category)}) as response:
                        if response.status == 429 or response.status >= 500:
                            if attempt == 0:
                                await asyncio.sleep(1.5)
                                continue
                            break
                        response.raise_for_status()
                        payload = await response.json(content_type=None)
                        return payload.get("elements", [])
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    if attempt == 0:
                        await asyncio.sleep(1.5)
        raise RuntimeError("overpass_unavailable")


async def _discover(job_id: str) -> int:
    async def work(session):
        job = await session.get(DiscoveryJob, job_id)
        if not job:
            return 0
        job.status = "running"
        await session.flush()
        await session.commit()
        try:
            elements = await _fetch_overpass(job.bbox, job.category)
        except Exception:
            job.status = "failed"
            job.error_code = "source_unavailable"
            job.completed_at = datetime.now(timezone.utc)
            logger.warning("Discovery failed job_id=%s error_code=source_unavailable", job_id)
            return 0
        count = 0
        values_batch = []
        for item in elements:
            tags = item.get("tags") or {}
            name = tags.get("name")
            if not name:
                continue
            center = item.get("center") or item
            if center.get("lat") is None or center.get("lon") is None:
                continue
            address = ", ".join(
                filter(
                    None,
                    (
                        tags.get("addr:housenumber"),
                        tags.get("addr:street"),
                        tags.get("addr:city"),
                        tags.get("addr:postcode"),
                        tags.get("addr:country"),
                    ),
                )
            ) or None
            values_batch.append(
                {
                    "account_id": job.account_id,
                    "job_id": job.id,
                    "source_key": f"osm:{item.get('type')}:{item.get('id')}",
                    "name": name[:300],
                    "latitude": center["lat"],
                    "longitude": center["lon"],
                    "category": job.category,
                    "address": address,
                    "website": tags.get("website") or tags.get("contact:website"),
                    "phone": tags.get("phone") or tags.get("contact:phone"),
                    "tags": tags,
                }
            )
            count += 1
        if values_batch:
            stmt = insert(DiscoveredPlace).values(values_batch).on_conflict_do_update(
                index_elements=["account_id", "source_key"],
                set_={
                    "job_id": insert(DiscoveredPlace).excluded.job_id,
                    "name": insert(DiscoveredPlace).excluded.name,
                    "latitude": insert(DiscoveredPlace).excluded.latitude,
                    "longitude": insert(DiscoveredPlace).excluded.longitude,
                    "category": insert(DiscoveredPlace).excluded.category,
                    "address": insert(DiscoveredPlace).excluded.address,
                    "website": insert(DiscoveredPlace).excluded.website,
                    "phone": insert(DiscoveredPlace).excluded.phone,
                    "tags": insert(DiscoveredPlace).excluded.tags,
                },
            )
            await session.execute(stmt)
        job.status = "completed"
        job.result_count = count
        job.completed_at = datetime.now(timezone.utc)
        return count
    from tasks._bridge import run_async

    return run_async(work)


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


async def _public_host(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        answers = await asyncio.to_thread(
            socket.getaddrinfo,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
        addresses = {ipaddress.ip_address(answer[4][0]) for answer in answers}
        return bool(addresses) and all(address.is_global for address in addresses)
    except (OSError, ValueError):
        return False


class _PublicResolver(AbstractResolver):
    """Pin DNS resolution to public addresses to prevent redirects/rebinding into private networks."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        records = await asyncio.to_thread(socket.getaddrinfo, host, port, family, socket.SOCK_STREAM)
        results = []
        for record_family, _, proto, _, sockaddr in records:
            address = ipaddress.ip_address(sockaddr[0])
            if not address.is_global:
                raise OSError("non_public_address")
            results.append(
                {
                    "hostname": host,
                    "host": sockaddr[0],
                    "port": port,
                    "family": record_family,
                    "proto": proto,
                    "flags": 0,
                }
            )
        if not results:
            raise OSError("host_unresolved")
        return results

    async def close(self):
        return None


async def _scrape(url: str) -> dict:
    if not await _public_host(url):
        return {"error": "invalid_public_url"}
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls = [
        urljoin(base, "/"),
        *(urljoin(base, path) for path in ("/contact", "/about", "/impressum", "/privacy")),
    ]
    emails, phones, socials, forms, signals = set(), set(), set(), False, set()
    connector = aiohttp.TCPConnector(limit_per_host=1, resolver=_PublicResolver())
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=8, connect=3),
        connector=connector,
        headers={"User-Agent": "Plantiers-OutreachOS/1.0 (public website contact details)"},
    ) as session:
        for page_url in urls:
            try:
                async with session.get(page_url, allow_redirects=False) as response:
                    if response.status != 200 or "text/html" not in response.headers.get("Content-Type", ""):
                        continue
                    html = (await response.content.read(1_000_000)).decode(
                        response.charset or "utf-8",
                        errors="replace",
                    )
                parser = _Text()
                parser.feed(html)
                text = " ".join(parser.parts)
                emails.update(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", html, re.I))
                phones.update(re.findall(r"(?:\+?\d[\d .()/-]{7,}\d)", text))
                social_pattern = (
                    r"https?://(?:www\.)?(?:linkedin\.com|instagram\.com|facebook\.com|"
                    r"x\.com|twitter\.com|wa\.me)/[^\s\"'<>]+"
                )
                socials.update(
                    re.findall(social_pattern, html, re.I)
                )
                forms = forms or "<form" in html.lower()
                for signal in ("wordpress", "shopify", "wix", "webflow", "prestashop"):
                    if signal in html.lower():
                        signals.add(signal)
            except (aiohttp.ClientError, TimeoutError, ValueError):
                continue
    return {
        "emails": sorted(emails),
        "phones": sorted(phones),
        "socials": sorted(socials),
        "has_form": forms,
        "technologies": sorted(signals),
        "language": None,
    }


async def _enrich(job_id: str) -> bool:
    async def work(session):
        job = await session.get(EnrichmentJob, job_id)
        if not job:
            return False
        job.status = "running"
        await session.flush()
        await session.commit()
        lead = await session.get(Lead, job.lead_id)
        if not lead or not lead.company:
            job.status = "completed"
            return True
        rows = await session.execute(
            select(DiscoveredPlace.website)
            .where(
                DiscoveredPlace.account_id == job.account_id,
                DiscoveredPlace.lead_id == lead.id,
                DiscoveredPlace.website.is_not(None),
            )
            .limit(1)
        )
        url = rows.scalar_one_or_none()
        if not url:
            job.status = "completed"
            return True
        await session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(url, 0)))
        )
        cached = await session.scalar(
            select(PublicPageCache).where(
                PublicPageCache.url == url,
                PublicPageCache.expires_at > datetime.now(timezone.utc),
            )
        )
        data = cached.data if cached else await _scrape(url)
        now = datetime.now(timezone.utc)
        if not cached:
            ttl = timedelta(hours=6) if data.get("error") else timedelta(days=30)
            cache_stmt = insert(PublicPageCache).values(
                url=url,
                status="failed" if data.get("error") else "completed",
                data=data,
                source_url=url,
                source_type="public_website",
                confidence=0.0 if data.get("error") else 0.75,
                collected_at=now,
                expires_at=now + ttl,
            )
            stmt = cache_stmt.on_conflict_do_update(
                index_elements=["url"],
                set_={
                    "status": "failed" if data.get("error") else "completed",
                    "data": data,
                    "source_url": url,
                    "source_type": "public_website",
                    "confidence": 0.0 if data.get("error") else 0.75,
                    "collected_at": now,
                    "expires_at": now + ttl,
                },
            )
            await session.execute(stmt)
        if data.get("emails") and not lead.email:
            lead.email = data["emails"][0]
        if data.get("phones") and not lead.phone:
            lead.phone = data["phones"][0]
        contact = await session.scalar(
            select(Contact)
            .where(
                Contact.lead_id == lead.id,
                Contact.account_id == job.account_id,
                Contact.deleted_at.is_(None),
            )
            .order_by(Contact.is_primary.desc())
            .limit(1)
        )
        if contact:
            if data.get("emails") and not contact.email:
                contact.email = data["emails"][0]
            if data.get("phones") and not contact.phone:
                contact.phone = data["phones"][0]
        job.status = "completed"
        return True
    from tasks._bridge import run_async

    return run_async(work)


@celery_app.task(name="tasks.prospecting_tasks.discover", bind=True, max_retries=2)
def discover_task(self, job_id: str):
    try:
        return _discover(job_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=15 * (self.request.retries + 1))


@celery_app.task(name="tasks.prospecting_tasks.enrich", bind=True, max_retries=2)
def enrich_task(self, job_id: str):
    try:
        return _enrich(job_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=15 * (self.request.retries + 1))
