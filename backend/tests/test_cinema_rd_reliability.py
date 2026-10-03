from unittest.mock import patch
import hashlib
import httpx
import pytest
from sqlalchemy.orm import Session
import test_cinema
from houseos import cinema as c, cinema_adapters as a


def client_fixture(responses):
    original = httpx.Client
    calls = []

    def handler(request):
        calls.append(request)
        status, body = responses.pop(0)
        return (
            httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)
        )

    transport = httpx.MockTransport(handler)
    return patch.object(
        a.httpx, "Client", side_effect=lambda **kwargs: original(transport=transport, **kwargs)
    ), calls


def test_rejection_retains_code_and_operation_without_upstream_content():
    context, calls = client_fixture([(451, {"error_code": 35, "error": "secret signed media URL"})])
    with context, patch.object(a, "rd_rate_limit"):
        with pytest.raises(a.DebridError) as caught:
            a.RealDebrid({"enabled": True, "token": "fixture", "entitlement_confirmed": True}).add("a" * 40)
    result = caught.value.public()
    assert (
        result["provider_code"] == 35 and result["http_status"] == 451 and result["operation"] == "add_magnet"
    )
    assert result["code"] == "SOURCE_REJECTED" and not result["retryable"]
    assert "secret" not in str(result) and len(calls) == 1


def test_only_definitive_transient_rejection_retries_add():
    context, calls = client_fixture([(503, {"error_code": 6}), (201, {"id": "exact"})])
    with context, patch.object(a, "rd_rate_limit"), patch.object(a.time, "sleep"):
        assert (
            a.RealDebrid({"enabled": True, "token": "fixture", "entitlement_confirmed": True}).add("a" * 40)
            == "exact"
        )
    assert len(calls) == 2
    context, calls = client_fixture([(500, "not json")])
    with context, patch.object(a, "rd_rate_limit"):
        with pytest.raises(a.DebridError) as caught:
            a.RealDebrid({"enabled": True, "token": "fixture", "entitlement_confirmed": True}).add("a" * 40)
    assert (
        caught.value.code == "ACCOUNT_ACTION_UNCERTAIN"
        and caught.value.provider_code is None
        and len(calls) == 1
    )


def test_cached_transition_gets_bounded_ready_poll():
    rd = a.RealDebrid({"enabled": True, "token": "fixture", "entitlement_confirmed": True})
    downloaded = {"status": "downloaded", "files": [{"id": 1, "selected": 1}], "links": ["fixture-link"]}
    with (
        patch.object(rd, "info", side_effect=[{"status": "queued"}, downloaded]),
        patch.object(rd, "call", return_value={"download": "https://example.com/file", "filesize": 123}),
        patch.object(a, "public_url"),
        patch.object(a.time, "sleep"),
    ):
        assert rd.resolve("torrent", "1", wait_seconds=2) == ("https://example.com/file", 123)
    with patch.object(rd, "info", return_value={"status": "downloading", "progress": 12}):
        with pytest.raises(a.MediaError) as caught:
            rd.resolve("torrent", "1")
    assert caught.value.code == "SOURCE_DOWNLOADING"


@pytest.mark.parametrize(
    "error,uncertain",
    [(a.DebridError(35, 451, "add_magnet"), False), (a.DebridError(None, 500, "add_magnet"), True)],
)
def test_definitive_vs_unknown_add_state(error, uncertain):
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(c.CinemaWorkflow, "workflow-one")
            row.state = "preparing"
            row.device_id = None
            row.data = {
                **row.data,
                "_sources": [
                    {
                        "id": "source-one",
                        "info_hash": "a" * 40,
                        "release": "Fixture",
                        "layer": "ON_DEMAND",
                        "state": "discovered",
                    }
                ],
            }
            db.commit()
            with (
                patch.object(c, "RealDebrid") as rd,
                patch.object(c, "integration_config", return_value={"token": "fixture"}),
            ):
                rd.return_value.add.side_effect = error
                c.validate_rd(db, row, ["source-one"])
            source = row.data["_sources"][0]
            assert source["add_uncertain"] is uncertain
            assert source["error"]["provider_code"] == error.provider_code
            assert row.data["error"]["code"] == error.code
            assert c.public_workflow(row)["validation_summary"]["errors"] == {error.code: 1}
    finally:
        f.tearDown()


def test_recent_exact_title_account_rejection_is_ranked_after_other_sources():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(c.CinemaWorkflow, "workflow-one")
            row.data = {
                **row.data,
                "_rd_account_key": hashlib.sha256(b"fixture").hexdigest()[:24],
                "_sources": [
                    {"info_hash": "a" * 40, "error": a.DebridError(35, 451, "unrestrict_link").public()}
                ],
            }
            db.commit()
        with (
            patch.object(c, "Comet") as comet,
            patch.object(c, "RealDebrid") as rd,
            patch.object(
                c,
                "integration_config",
                side_effect=lambda db, name: (
                    {}
                    if name == "stream_addon"
                    else {"enabled": True, "token": "fixture", "entitlement_confirmed": True}
                ),
            ),
        ):
            comet.return_value.streams.return_value = [
                {"info_hash": "a" * 40, "release": "Rejected", "height_claim": 2160},
                {"info_hash": "b" * 40, "release": "Unknown", "height_claim": 720},
            ]
            rd.return_value.inventory.return_value = []
            response = f.client.post(
                "/api/v1/cinema/discover", json={"media_id": f.title_id, "idempotency_key": "retry-discovery"}
            ).json()
        assert response["provisional"][0]["release"] == "Unknown"
        assert (
            response["provisional"][1]["error"]["provider_code"] == 35
            and response["provisional"][1]["rd_cached"] is False
        )
    finally:
        f.tearDown()


def test_add_retry_rechecks_authorization_before_second_mutation():
    context, calls = client_fixture([(503, {"error_code": 6})])
    checks = []

    def check():
        checks.append(True)
        if len(checks) == 2:
            raise a.MediaError("PERMISSION_REVOKED", "Cancelled")

    with context, patch.object(a, "rd_rate_limit"), patch.object(a.time, "sleep"):
        with pytest.raises(a.MediaError) as caught:
            a.RealDebrid({"enabled": True, "token": "fixture", "entitlement_confirmed": True}).add(
                "a" * 40, check=check
            )
    assert caught.value.code == "PERMISSION_REVOKED" and len(calls) == 1 and len(checks) == 2


def test_inventory_and_accepted_selection_race_are_bounded():
    rd = a.RealDebrid({"enabled": True, "token": "fixture", "entitlement_confirmed": True})
    with patch.object(rd, "call", return_value=[]) as call:
        rd.inventory()
        assert call.call_args.kwargs["params"] == {"limit": 500}
    downloaded = {"status": "downloaded", "files": [{"id": 5, "selected": 1}], "links": ["fixture-link"]}
    with (
        patch.object(rd, "info", side_effect=[{"status": "waiting_files_selection"}, downloaded]),
        patch.object(rd, "call", return_value={"download": "https://example.com/file", "filesize": 123}),
        patch.object(a, "public_url"),
        patch.object(a.time, "sleep"),
    ):
        assert rd.resolve("torrent", "5", wait_seconds=2, selection_pending=True) == (
            "https://example.com/file",
            123,
        )
    with (
        patch.object(rd, "info", return_value={"status": "waiting_files_selection"}),
        patch.object(a.time, "sleep") as sleep,
    ):
        with pytest.raises(a.MediaError) as caught:
            rd.resolve("torrent", "5", wait_seconds=2)
        assert caught.value.code == "SOURCE_SELECTION_REQUIRED"
        sleep.assert_not_called()


def test_failed_inspection_cannot_be_chosen_but_can_be_revalidated():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(c.CinemaWorkflow, "workflow-one")
            source = {
                **row.data["_sources"][0],
                "info_hash": "a" * 40,
                "error": a.MediaError("SOURCE_DOWNLOADING", "Still downloading", "resolve").public(),
            }
            row.data = {**row.data, "_sources": [source]}
            db.commit()
            assert c.freeze_choices(row, db.get(c.CinemaDevice, row.device_id))["candidates"] == []
        with patch.object(c, "RealDebrid"), patch.object(c, "integration_config", return_value={}):
            response = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/validate",
                json={"version": 1, "source_ids": ["source-one"]},
            )
        assert response.status_code == 200
        assert response.json()["confirmation_id"]
    finally:
        f.tearDown()
