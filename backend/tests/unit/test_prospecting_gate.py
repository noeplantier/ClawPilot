"""Map discovery and site enrichment read the network: both routes refuse unless FEATURE_EXTERNAL_SOURCES is on."""

import inspect

import pytest
from fastapi import HTTPException

from routes import prospecting


def test_the_gate_refuses_with_409_when_the_flag_is_off(monkeypatch):
    monkeypatch.delenv("FEATURE_EXTERNAL_SOURCES", raising=False)
    with pytest.raises(HTTPException) as refused:
        prospecting._need_external_sources()
    assert refused.value.status_code == 409
    assert "FEATURE_EXTERNAL_SOURCES" in refused.value.detail


def test_the_gate_lets_the_request_through_when_the_flag_is_on(monkeypatch):
    monkeypatch.setenv("FEATURE_EXTERNAL_SOURCES", "true")
    assert prospecting._need_external_sources() is None


@pytest.mark.parametrize("route", [prospecting.search, prospecting.enqueue_enrichment])
def test_both_network_routes_check_the_flag_before_reading_the_database(route):
    source = inspect.getsource(route)
    assert source.index("_need_external_sources()") < source.index("session.")
