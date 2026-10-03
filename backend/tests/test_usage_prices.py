"""AI usage: prices looked up from OpenRouter's public list, only for models the house uses,
never for subscriptions; unpriced API requests get an estimate."""

from houseos import usage_prices
from houseos.models import Integration, Usage
from test_core import admin

CATALOGUE = {
    "data": [
        {"id": "deepseek/deepseek-v4-flash", "pricing": {"prompt": "0.0000001", "completion": "0.0000004"}},
        {
            "id": "anthropic/claude-opus-5.5",
            "pricing": {"prompt": "0.000005", "completion": "0.000025", "input_cache_read": "0.0000005"},
        },
        {
            "id": "anthropic/claude-opus-5.5:batch",
            "pricing": {"prompt": "0.0000025", "completion": "0.0000125"},
        },
    ]
}


def test_matching_names_across_providers():
    entries = {e["id"]: e for e in CATALOGUE["data"]}
    assert usage_prices.match("anthropic", "claude-opus-5-5", entries)["id"] == "anthropic/claude-opus-5.5"
    assert (
        usage_prices.match("openrouter", "deepseek/deepseek-v4-flash", entries)["id"]
        == "deepseek/deepseek-v4-flash"
    )
    assert usage_prices.match("openai", "gpt-unknown", entries) is None


def test_look_up_prices_then_estimate_unpriced_requests(client, monkeypatch):
    c, db = client
    me = admin(client)
    db.add(
        Integration(
            name="anthropic", config={"auth_mode": "claude_code", "model": "claude-opus-5-5"}, enabled=True
        )
    )
    db.add(
        Usage(
            user_id=me["id"],
            provider="openrouter",
            model="deepseek/deepseek-v4-flash",
            input_tokens=1_000_000,
            output_tokens=100_000,
            status="completed",
        )
    )
    db.add(
        Usage(
            user_id=me["id"],
            provider="anthropic",
            model="claude-opus-5-5",
            input_tokens=5000,
            output_tokens=500,
            status="completed",
        )
    )
    db.commit()

    pages = {
        "deepseek/deepseek-v4-flash": [
            {"provider_name": "Relace", "pricing": {"prompt": "0.00000003", "completion": "0.00000128"}},
            {"provider_name": "Other", "pricing": {"prompt": "0.00000004", "completion": "0.0000005"}},
        ]
    }

    class Reply:
        def __init__(self, body):
            self.body, self.is_success = body, True

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    class Fake:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url, **_):
            if url == usage_prices.CATALOGUE:
                return Reply(CATALOGUE)
            model = url.split("/models/")[1].removesuffix("/endpoints")
            return Reply({"data": {"endpoints": pages.get(model, [])}})

    monkeypatch.setattr(usage_prices.httpx, "Client", Fake)
    result = c.post("/api/v1/admin/usage/prices").json()
    assert result["priced"] == 1  # the Claude sign-in is a subscription: not priced by tokens
    totals = c.get("/api/v1/usage?days=7").json()["totals"]
    assert totals["looked_up_requests"] == 1
    assert totals["looked_up_microusd"] == 158_000  # the page's first price: 1M × $0.03 + 100k × $1.28/M
