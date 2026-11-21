from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app import mappings
from app.financials import identity


class EmptyProposalRunner:
    limits = SimpleNamespace(tpm=100_000)

    def __call__(self, body, validate):
        response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": '{"proposals": []}'},
                }
            ]
        }
        validate(response)
        return response


def test_investigate_handles_null_sec_units_labels_and_descriptions(monkeypatch):
    monkeypatch.setattr(mappings.settings, "groq_api_key", "mock-key")
    end = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    start = (datetime.fromisoformat(end) - timedelta(days=90)).date().isoformat()
    filed = datetime.now(UTC).date().isoformat()
    facts = {
        "facts": {
            "us-gaap": {
                "RevenueExtension": {
                    "label": None,
                    "description": None,
                    "units": {
                        "USD": [
                            {
                                "start": start,
                                "end": end,
                                "filed": filed,
                                "form": "10-Q",
                                "val": 100,
                            }
                        ]
                    },
                },
                "MissingUnitsExtension": {
                    "label": None,
                    "description": None,
                    "units": None,
                },
            }
        }
    }

    result = mappings.investigate(
        facts,
        {"version": mappings.VERSION, "mappings": [], "attempts": []},
        EmptyProposalRunner(),
    )

    assert result["attempts"]
    assert all(attempt["status"] == "completed" for attempt in result["attempts"])
    assert result["mappings"] == []


def test_apply_mappings_handles_null_sec_definitions():
    facts = {
        "facts": {
            "issuer": {
                "CashFlowExtension": {
                    "label": None,
                    "description": None,
                    "units": {},
                }
            }
        }
    }
    digest = identity({"label": "", "description": ""})
    registry = {
        "mappings": [
            {
                "status": "accepted",
                "metric": "operating_cash_flow",
                "namespace": "issuer",
                "tag": "CashFlowExtension",
                "definition_digest": digest,
                "id": "test-map",
                "reason": "Test mapping",
            }
        ]
    }

    mapped, overrides, notes = mappings.apply_mappings(facts, registry)

    assert overrides == {"operating_cash_flow": ["mapped_operating_cash_flow_test-map"]}
    assert notes["mapped_operating_cash_flow_test-map"]["tag"] == "CashFlowExtension"
    assert "mapped_operating_cash_flow_test-map" in mapped["facts"]["us-gaap"]
