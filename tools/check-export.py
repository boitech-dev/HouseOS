#!/usr/bin/env python3
"""Safe local smoke check: no external services, device commands or persistent DB."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from houseos.config import settings
from houseos.main import app
from houseos.integrations import check_config
from fastapi import HTTPException
from fastapi.testclient import TestClient
assert settings.allowed_origins=='http://127.0.0.1:8990'
assert not settings.database_url and not settings.encryption_key and not settings.bootstrap_token
assert not settings.audio_enabled and not settings.external_fetch_enabled
assert not settings.cast_lan_cidr and not settings.receiver_base_url
with TestClient(app) as client:
    result=client.get('/')
    assert result.status_code==200 and '<html' in result.text.lower()
    assert client.post('/api/v1/auth/login',headers={'Origin':'https://untrusted.example'},json={}).status_code==403
# Both physical destinations and receiver delivery require recipient approval/configuration.
for config in ({'host':'192.0.2.32'},{'receiver_base_url':'http://192.0.2.10:8991'}):
    try:check_config('cast',config)
    except HTTPException as exc:assert exc.status_code==422
    else:raise AssertionError('Unconfigured receiver accepted')
print('PASS: built UI, origin boundary, blank secrets, disabled outputs, fail-closed receiver enrollment.')
