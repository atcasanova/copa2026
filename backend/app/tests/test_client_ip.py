import os
import pytest
from unittest.mock import MagicMock
from fastapi import Request
from app.routers.auth import get_client_ip, get_trusted_proxies_networks, is_trusted_proxy

def create_mock_request(peer_ip: str, headers: dict) -> Request:
    request = MagicMock(spec=Request)
    request.client = MagicMock()
    request.client.host = peer_ip
    request.headers = headers
    return request

def test_trusted_proxy_detection():
    # Loopback and private ranges should be trusted by default
    networks = get_trusted_proxies_networks()
    assert is_trusted_proxy("127.0.0.1", networks)
    assert is_trusted_proxy("172.30.0.1", networks)
    assert is_trusted_proxy("10.0.0.5", networks)
    
    # Public IP should not be trusted
    assert not is_trusted_proxy("203.0.113.195", networks)

def test_get_client_ip_from_trusted_proxy():
    # Peer is a trusted proxy (e.g. 172.30.0.1)
    # CF-Connecting-IP should take precedence
    req1 = create_mock_request(
        peer_ip="172.30.0.1",
        headers={
            "cf-connecting-ip": "203.0.113.195",
            "x-real-ip": "198.51.100.22",
            "x-forwarded-for": "198.51.100.22, 172.30.0.1"
        }
    )
    assert get_client_ip(req1) == "203.0.113.195"

    # X-Real-IP is fallback if CF-Connecting-IP is missing
    req2 = create_mock_request(
        peer_ip="172.30.0.1",
        headers={
            "x-real-ip": "198.51.100.22",
            "x-forwarded-for": "198.51.100.22, 172.30.0.1"
        }
    )
    assert get_client_ip(req2) == "198.51.100.22"

    # X-Forwarded-For is fallback if X-Real-IP is missing
    req3 = create_mock_request(
        peer_ip="172.30.0.1",
        headers={
            "x-forwarded-for": "198.51.100.33, 172.30.0.1"
        }
    )
    assert get_client_ip(req3) == "198.51.100.33"

def test_get_client_ip_from_untrusted_peer():
    # Peer is NOT trusted (e.g. direct connection from public IP)
    # All headers should be completely ignored
    req = create_mock_request(
        peer_ip="203.0.113.44",
        headers={
            "cf-connecting-ip": "8.8.8.8",
            "x-real-ip": "8.8.8.8",
            "x-forwarded-for": "8.8.8.8"
        }
    )
    assert get_client_ip(req) == "203.0.113.44"

def test_invalid_ips_ignored():
    # Invalid IPs in headers should be ignored, falling back
    req = create_mock_request(
        peer_ip="127.0.0.1",
        headers={
            "cf-connecting-ip": "invalid-ip",
            "x-real-ip": "198.51.100.55"
        }
    )
    assert get_client_ip(req) == "198.51.100.55"

def test_custom_trusted_proxies(monkeypatch):
    # Set a custom list of trusted proxies via env var
    monkeypatch.setenv("TRUSTED_PROXIES", "192.168.1.100,200.100.50.0/24")
    networks = get_trusted_proxies_networks()
    
    # Custom values should be trusted
    assert is_trusted_proxy("192.168.1.100", networks)
    assert is_trusted_proxy("200.100.50.45", networks)
    
    # Loopback or local docker subnet should NO LONGER be trusted since env overrides it
    assert not is_trusted_proxy("127.0.0.1", networks)
    assert not is_trusted_proxy("172.30.0.1", networks)
