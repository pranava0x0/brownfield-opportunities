"""Unit tests for Connector.http_get_json() — cache hit/miss + API error handling."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from connectors import base as base_module
from connectors.superfund_npl import SuperfundNPL


@pytest.fixture
def conn(tmp_path):
    return SuperfundNPL(cache_dir=tmp_path / "cache")


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


@patch.object(base_module.requests, "get")
@patch.object(base_module.time, "sleep", lambda _: None)
def test_first_fetch_hits_network_and_caches(mock_get, conn):
    mock_get.return_value = _mock_response({"features": [{"x": 1}]})

    data = conn.http_get_json("https://example.com", {"q": "1"}, use_cache=True)

    assert data == {"features": [{"x": 1}]}
    assert mock_get.call_count == 1
    cached = list(conn.cache_dir.glob("superfund-npl_*.json"))
    assert len(cached) == 1


@patch.object(base_module.requests, "get")
@patch.object(base_module.time, "sleep", lambda _: None)
def test_second_fetch_uses_cache(mock_get, conn):
    mock_get.return_value = _mock_response({"features": [{"x": 1}]})

    conn.http_get_json("https://example.com", {"q": "1"}, use_cache=True)
    conn.http_get_json("https://example.com", {"q": "1"}, use_cache=True)

    assert mock_get.call_count == 1


@patch.object(base_module.requests, "get")
@patch.object(base_module.time, "sleep", lambda _: None)
def test_no_cache_forces_refetch(mock_get, conn):
    mock_get.return_value = _mock_response({"features": []})

    conn.http_get_json("https://example.com", {"q": "1"}, use_cache=True)
    conn.http_get_json("https://example.com", {"q": "1"}, use_cache=False)

    assert mock_get.call_count == 2


@patch.object(base_module.requests, "get")
@patch.object(base_module.time, "sleep", lambda _: None)
def test_api_error_raises(mock_get, conn):
    mock_get.return_value = _mock_response({"error": {"code": 400, "message": "bad"}})
    with pytest.raises(RuntimeError, match="API error"):
        conn.http_get_json("https://example.com", {"q": "1"}, use_cache=False)


@patch.object(base_module.requests, "get")
@patch.object(base_module.time, "sleep", lambda _: None)
def test_distinct_params_distinct_cache_keys(mock_get, conn):
    mock_get.return_value = _mock_response({"features": []})

    conn.http_get_json("https://example.com", {"q": "A"}, use_cache=True)
    conn.http_get_json("https://example.com", {"q": "B"}, use_cache=True)

    assert mock_get.call_count == 2
    assert len(list(conn.cache_dir.glob("superfund-npl_*.json"))) == 2


@patch.object(base_module.requests, "get")
@patch.object(base_module.time, "sleep", lambda _: None)
def test_cache_file_is_valid_json(mock_get, conn):
    mock_get.return_value = _mock_response({"features": [{"x": 1, "y": 2}]})
    conn.http_get_json("https://example.com", {"q": "1"}, use_cache=True)
    cached_files = list(conn.cache_dir.glob("superfund-npl_*.json"))
    payload = json.loads(cached_files[0].read_text())
    assert payload == {"features": [{"x": 1, "y": 2}]}
