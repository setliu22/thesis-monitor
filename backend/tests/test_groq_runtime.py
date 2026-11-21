import json
import httpx
import pytest
from app.groq_runtime import GroqRunner, Deferred, Limits


def response():
    return {
        "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
        "usage": {"total_tokens": 100},
    }


def test_cache_survives_runner_restart_and_changes_with_request(sessions):
    calls = []

    def send(request):
        calls.append(request)
        return httpx.Response(200, json=response())

    body = {
        "model": "test",
        "messages": [{"role": "user", "content": "same source and thesis"}],
        "max_completion_tokens": 100,
    }
    first = GroqRunner(sessions, "test-key", transport=httpx.MockTransport(send))
    first(body, lambda p: p["choices"])
    GroqRunner(sessions, "test-key", transport=httpx.MockTransport(send))(
        body, lambda p: p["choices"]
    )
    assert len(calls) == 1
    first(body | {"model": "another"}, lambda p: p["choices"])
    assert len(calls) == 2


def test_shared_budget_defers_without_network_or_sleep(sessions):
    calls = []

    def send(r):
        calls.append(r)
        return httpx.Response(200, json=response())

    limits = Limits(tpm=10000, tpd=100000, rpm=1, rpd=1000)
    body = {"model": "test", "messages": [], "max_completion_tokens": 100}
    GroqRunner(sessions, "key", limits=limits, transport=httpx.MockTransport(send))(
        body, lambda p: None
    )
    with pytest.raises(Deferred) as exc:
        GroqRunner(sessions, "key", limits=limits, transport=httpx.MockTransport(send))(
            body | {"model": "new"}, lambda p: None
        )
    assert exc.value.delay > 0
    assert len(calls) == 1


def test_provider_429_is_durable_and_does_not_cache_failure(sessions):
    calls = []

    def send(r):
        calls.append(r)
        return httpx.Response(429, headers={"retry-after": "120"})

    body = {"model": "test", "messages": [], "max_completion_tokens": 100}
    runner = GroqRunner(sessions, "secret-key", transport=httpx.MockTransport(send))
    with pytest.raises(Deferred) as exc:
        runner(body, lambda p: None)
    assert exc.value.delay >= 120
    assert "secret" not in str(exc.value)
    with pytest.raises(Deferred):
        GroqRunner(sessions, "key", transport=httpx.MockTransport(send))(
            body, lambda p: None
        )
    assert len(calls) == 1


def test_invalid_output_never_becomes_reusable_checkpoint(sessions):
    calls = []

    def send(r):
        calls.append(r)
        return httpx.Response(200, json=response())

    runner = GroqRunner(sessions, "key", transport=httpx.MockTransport(send))

    def reject(p):
        raise ValueError("Invalid decisions")

    for _ in range(2):
        with pytest.raises(ValueError):
            runner(
                {"model": "test", "messages": [], "max_completion_tokens": 100}, reject
            )
    assert len(calls) == 2


def test_many_stocks_resume_batches_without_repeating_successful_calls(sessions):
    from app.transcripts import compare_transcript
    from app.analysis import AnalysisConfig

    at = [1000000.0]
    calls = []

    def send(request):
        body = json.loads(request.content)
        supplied = json.loads(body["messages"][1]["content"])
        calls.append(body)
        matches = {p["id"]: "T1" for p in supplied["filing_passages"]}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps({"matches": matches})},
                    }
                ],
                "usage": {"total_tokens": 1500},
            },
        )

    sources = [
        {
            "symbol": f"TEST{i}",
            "quarter": "2025Q4",
            "source_url": "https://example.org",
            "turns": [
                {
                    "turn": j + 1,
                    "speaker": "CEO",
                    "content": f"Company {i} warehouse expansion project {j} supports planned sales growth.",
                }
                for j in range(95)
            ],
        }
        for i in range(10)
    ]
    completed = set()
    deferrals = 0
    for _ in range(500):
        if len(completed) == len(sources):
            break
        for i, source in enumerate(sources):
            if i in completed:
                continue
            runner = GroqRunner(
                sessions,
                "key",
                transport=httpx.MockTransport(send),
                clock=lambda: at[0],
            )
            try:
                result = compare_transcript(
                    source,
                    "Warehouse expansion supports sales growth.",
                    AnalysisConfig("key"),
                    runner=runner,
                )
                assert result["coverage"]["full_transcript"]
                assert result["coverage"]["passages_classified"] == 95
                completed.add(i)
            except Deferred:
                deferrals += 1
        at[0] += 61
    assert len(completed) == 10
    assert deferrals > 0
    assert len(calls) == 30  # 3 distinct batches per company, including after restart.


def test_daily_limit_waits_until_next_window(sessions):
    at = [1000000.0]
    body = {"model": "test", "messages": [], "max_completion_tokens": 100}
    limits = Limits(tpm=10000, tpd=10000, rpm=100, rpd=1)
    runner = GroqRunner(
        sessions,
        "key",
        limits=limits,
        clock=lambda: at[0],
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response())),
    )
    runner(body, lambda p: None)
    with pytest.raises(Deferred) as exc:
        runner(body | {"model": "new"}, lambda p: None)
    assert exc.value.delay > 86000
    at[0] += 86401
    runner(body | {"model": "new"}, lambda p: None)


def test_mapping_requests_keep_all_candidates_within_budget():
    from app.mappings import mapping_requests
    from app.groq_runtime import estimate

    payload = {
        "missing_metrics": ["revenue"],
        "period": "2026-09-30",
        "candidates": [
            {
                "tag": f"tag{i}",
                "description": "Definition of a possible equivalent source tag. " * 18,
            }
            for i in range(100)
        ],
    }
    body = {
        "model": "test",
        "max_completion_tokens": 1800,
        "messages": [
            {"role": "system", "content": "Return equivalent tags."},
            {"role": "user", "content": ""},
        ],
    }
    batches = mapping_requests(body, payload, 7200)
    assert len(batches) > 1
    assert all(estimate(b) <= 7200 for b in batches)
    tags = [
        c["tag"]
        for b in batches
        for c in json.loads(b["messages"][1]["content"])["candidates"]
    ]
    assert tags == [c["tag"] for c in payload["candidates"]]


def test_postgres_workers_share_atomic_quota_reservations(sessions):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    if sessions.kw["bind"].dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    barrier = Barrier(2)

    def reserve(_):
        barrier.wait(timeout=5)
        runner = GroqRunner(
            sessions, "key", limits=Limits(rpm=1), clock=lambda: 1000000.0
        )
        try:
            runner.reserve(1000)
            return "admitted"
        except Deferred:
            return "deferred"

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(reserve, range(2)))
    assert sorted(result) == ["admitted", "deferred"]


def test_provider_cached_prompt_tokens_do_not_consume_daily_allowance(sessions):
    p = response()
    p["usage"] = {"total_tokens": 1000, "prompt_tokens_details": {"cached_tokens": 800}}
    runner = GroqRunner(
        sessions,
        "key",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=p)),
    )
    runner(
        {"model": "test", "messages": [], "max_completion_tokens": 100}, lambda p: None
    )
    assert runner.tokens == 200


def test_dns_failure_releases_request_allowance_and_retains_retry_reason(sessions):
    import socket

    calls = []

    def send(request):
        calls.append(request)
        if len(calls) == 1:
            try:
                raise socket.gaierror("Temporary failure in name resolution")
            except socket.gaierror as exc:
                raise httpx.ConnectError("DNS error") from exc
        return httpx.Response(200, json=response())

    limits = Limits(rpm=1)
    body = {"model": "test", "messages": [], "max_completion_tokens": 100}
    transport = httpx.MockTransport(send)
    runner = GroqRunner(sessions, "key", limits=limits, transport=transport)
    with pytest.raises(Deferred, match="could not resolve") as deferred:
        runner(body, lambda p: None)
    assert deferred.value.kind == "groq_provider"
    # An attempt that never connected cannot exhaust the request budget.
    resumed = GroqRunner(sessions, "key", limits=limits, transport=transport)
    assert resumed(body, lambda p: None) == response()
    assert len(calls) == 2
