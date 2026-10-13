"""Real HTTP path to model providers, against a local wire-compatible stand-in (no network, no key)."""

import pytest

from nis.agents import providers as prov
from nis.agents.providers import ProviderUnavailable, get_provider
from nis.config import get_settings

from fake_llm import FakeLLM  # tests/ is on sys.path (rootdir-relative, no package)


@pytest.fixture
def novel_for_models(writer):
    p = writer.project("رواية المزوّد")
    ch = writer.node(p["id"], "chapter", "الأول")
    writer.write(ch["document_id"], "كان البحر هادئاً في المساء.\n\nوقف نادر عند الرصيف ينتظر.")
    return writer, p


@pytest.fixture
def configure(monkeypatch):
    def _set(**env):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()
    monkeypatch.setattr(prov.time, "sleep", lambda s: None)   # retries without real waiting
    yield _set
    monkeypatch.undo()
    get_settings.cache_clear()


def test_no_built_in_model_the_operator_must_choose(configure):
    configure(NIS_LLM_PROVIDER="anthropic", NIS_LLM_API_KEY="k")
    p = get_provider()
    assert not p.available() and "NIS_LLM_MODEL" in p.describe()["message"]


def test_anthropic_wire_format_retries_transient_errors_and_reports_usage(configure):
    with FakeLLM() as f:
        configure(NIS_LLM_PROVIDER="anthropic", NIS_LLM_API_KEY="test-key", NIS_LLM_MODEL="model-x", NIS_LLM_BASE_URL=f.url)
        f.fail_next = [429, 529]
        f.reply = "جاهز"
        c = get_provider().complete("نظام", "سؤال", 16)
        assert c.text == "جاهز" and (c.input_tokens, c.output_tokens) == (120, 30)
        assert len(f.requests) == 3                                  # two transient failures, then success
        h, b = f.requests[-1]["headers"], f.requests[-1]["body"]
        assert h["x-api-key"] == "test-key" and h["anthropic-version"] and f.requests[-1]["path"] == "/v1/messages"
        assert b["model"] == "model-x" and b["system"] == "نظام" and b["max_tokens"] == 16


def test_permanent_errors_fail_fast_in_arabic(configure):
    with FakeLLM() as f:
        configure(NIS_LLM_PROVIDER="openai_compatible", NIS_LLM_BASE_URL=f.url, NIS_LLM_MODEL="m")
        f.fail_next = [401]
        with pytest.raises(ProviderUnavailable, match="رفض المفتاح"):
            get_provider().complete("s", "p")
        assert len(f.requests) == 1                                   # no retry on a rejected key
        f.fail_next = [503, 503, 503]
        with pytest.raises(ProviderUnavailable, match="بعد 3 محاولات"):
            get_provider().complete("s", "p")


def test_external_run_is_gated_then_metered_and_priced(novel_for_models, configure):
    w, p = novel_for_models
    with FakeLLM(host="127.0.0.2") as f:    # not localhost → treated as an external destination
        configure(NIS_LLM_PROVIDER="openai_compatible", NIS_LLM_BASE_URL=f.url + "/v1", NIS_LLM_MODEL="remote-m",
                  NIS_LLM_PRICE_IN_PER_MTOK="3", NIS_LLM_PRICE_OUT_PER_MTOK="15")
        r = w.run(p["id"], "A10", use_model=True)
        assert r.status_code == 403 and "127.0.0.2" in r.json()["destination"]
        assert not f.requests                                          # nothing left the machine before consent
        w.post(f"/v1/projects/{p['id']}/consents", json={"kind": "external_ai", "acknowledge_destination": r.json()["destination"]})
        assert w.run(p["id"], "A10", use_model=True).status_code == 428
        assert not f.requests
        run = w.run(p["id"], "A10", use_model=True, acknowledge_external=True, confirm_high_risk=True).json()
        assert run["status"] == "succeeded", run
        assert run["provider"] == "openai_compatible" and run["model_id"] == "remote-m"
        assert f.requests and all(x["path"] == "/v1/chat/completions" for x in f.requests)
        u = run["output"]["usage"]
        assert u["calls"] == len(f.requests) and u["input_tokens"] == 120 * u["calls"] and u["output_tokens"] == 30 * u["calls"]
        assert run["cost_estimate_usd"] == pytest.approx(u["input_tokens"] * 3e-6 + u["output_tokens"] * 15e-6)


def test_provider_check_sends_only_the_fixed_prompt(configure, capsys):
    from nis.cli import main
    from nis.ops import TEST_PROMPT

    with FakeLLM() as f:
        configure(NIS_LLM_PROVIDER="openai_compatible", NIS_LLM_BASE_URL=f.url, NIS_LLM_MODEL="local-m")
        assert main(["provider-check"]) == 0 and not f.requests     # no network without the flag
        f.reply = "جاهز"
        assert main(["provider-check", "--send-test-prompt"]) == 0
        assert len(f.requests) == 1 and f.requests[0]["body"]["messages"][1]["content"] == TEST_PROMPT
        assert "جاهز" in capsys.readouterr().out
