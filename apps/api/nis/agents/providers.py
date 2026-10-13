"""Model provider adapter (NFR10, FR25). Swapping providers never touches domain logic.

The default provider is `disabled`: the studio is fully usable for writing, bible, continuity, research and
deterministic analysis without any model. No price table is hard-coded: cost is only estimated when the
operator supplies prices via env (NIS_LLM_PRICE_IN_PER_MTOK / NIS_LLM_PRICE_OUT_PER_MTOK).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings


log = logging.getLogger("nis.provider")

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}
MAX_ATTEMPTS = 3
MAX_RETRY_AFTER_S = 20.0


class ProviderUnavailable(Exception):
    pass


def _post(url: str, *, headers: dict[str, str], body: dict[str, Any], timeout: float, who: str) -> dict[str, Any]:
    """POST with bounded retries on transient failures (rate limit, overload, 5xx, network), honouring
    Retry-After up to a cap. Permanent errors (bad key, bad request) fail at once with an Arabic message."""
    delay = 1.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=timeout)
        except httpx.TimeoutException as e:
            if attempt == MAX_ATTEMPTS:
                raise ProviderUnavailable(f"انتهت مهلة {who} ({timeout:.0f} ث) بعد {attempt} محاولات") from e
        except httpx.HTTPError as e:
            if attempt == MAX_ATTEMPTS:
                raise ProviderUnavailable(f"تعذّر الاتصال بـ{who}: {type(e).__name__}") from e
        else:
            if r.status_code < 400:
                return r.json()
            if r.status_code in (401, 403):
                raise ProviderUnavailable(f"{who} رفض المفتاح أو الصلاحية (HTTP {r.status_code}) — راجع NIS_LLM_API_KEY")
            if r.status_code == 404:
                raise ProviderUnavailable(f"{who}: المسار أو النموذج غير موجود (HTTP 404) — راجع NIS_LLM_MODEL وNIS_LLM_BASE_URL")
            if r.status_code not in RETRY_STATUS:
                raise ProviderUnavailable(f"{who} رفض الطلب (HTTP {r.status_code}) — راجع اسم النموذج وحدود الطلب")
            if attempt == MAX_ATTEMPTS:
                raise ProviderUnavailable(f"{who} مشغول أو محدود المعدّل (HTTP {r.status_code}) بعد {attempt} محاولات")
            try:
                delay = min(MAX_RETRY_AFTER_S, max(delay, float(r.headers.get("retry-after", delay))))
            except ValueError:
                pass
        log.warning("%s: transient failure, retry %d/%d in %.1fs", who, attempt, MAX_ATTEMPTS - 1, delay)
        time.sleep(delay)
        delay = min(MAX_RETRY_AFTER_S, delay * 3)
    raise ProviderUnavailable(f"تعذّر الوصول إلى {who}")  # unreachable


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class Provider:
    name = "disabled"
    external = False

    def available(self) -> bool:
        return False

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "available": self.available(), "external": self.external,
            "destination": "لا يوجد — الوكلاء يعملون بالتحليل الحتمي المحلي فقط",
            "model": "deterministic",
            "retention_note": "",
            "message": "لم يُفعَّل مزود نماذج. التحرير والبحث المحلي والتحليل الحتمي تعمل كاملة؛ "
                       "المهارات التوليدية تُعيد تنبيهاً واضحاً بدلاً من مخرجات مصطنعة.",
        }

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> Completion:
        raise ProviderUnavailable("مزود النماذج معطّل")


class AnthropicProvider(Provider):
    name = "anthropic"
    external = True

    def __init__(self) -> None:
        s = get_settings()
        self.key = s.llm_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = s.llm_model  # chosen by the operator; never a built-in default
        self.base = (s.llm_base_url or "https://api.anthropic.com").rstrip("/")
        self.timeout = s.llm_timeout_s

    def available(self) -> bool:
        return bool(self.key and self.model)

    def describe(self) -> dict[str, Any]:
        host = urlparse(self.base).hostname or self.base
        missing = [n for n, v in (("NIS_LLM_API_KEY", self.key), ("NIS_LLM_MODEL", self.model)) if not v]
        return {
            "name": self.name, "available": self.available(), "external": True,
            "destination": f"{host} (خدمة خارجية)", "model": self.model or "—",
            "retention_note": "سياسة الاحتفاظ والتدريب لدى المزود يجب مراجعتها في شروطه؛ النظام لا يفترضها.",
            "message": "يُرسل نص المخطوط إلى خدمة خارجية فقط بعد موافقة صريحة على مستوى المشروع والتشغيل."
            if self.available() else "غير مضبوط في بيئة الخادم: " + "، ".join(missing),
        }

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> Completion:
        if not self.available():
            raise ProviderUnavailable("المزوّد غير مضبوط (المفتاح أو اسم النموذج)")
        data = _post(f"{self.base}/v1/messages", timeout=self.timeout, who="مزوّد Anthropic",
                     headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                     body={"model": self.model, "max_tokens": max_tokens, "system": system,
                           "messages": [{"role": "user", "content": prompt}]})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        u = data.get("usage", {})
        return Completion(text, u.get("input_tokens", 0), u.get("output_tokens", 0), data.get("model", self.model))


class OpenAICompatibleProvider(Provider):
    """Any /chat/completions endpoint — typically a LOCAL model server (Ollama, LM Studio, vLLM)."""

    name = "openai_compatible"

    def __init__(self) -> None:
        s = get_settings()
        self.base = s.llm_base_url.rstrip("/")
        self.key = s.llm_api_key
        self.model = s.llm_model
        self.timeout = s.llm_timeout_s
        host = urlparse(self.base).hostname or ""
        self.external = host not in ("localhost", "127.0.0.1", "::1", "") and not host.endswith(".local")

    def available(self) -> bool:
        return bool(self.base and self.model)

    def describe(self) -> dict[str, Any]:
        missing = [n for n, v in (("NIS_LLM_BASE_URL", self.base), ("NIS_LLM_MODEL", self.model)) if not v]
        return {
            "name": self.name, "available": self.available(), "external": self.external,
            "destination": f"{self.base} ({'خارجي' if self.external else 'محلي على هذا الجهاز/الشبكة'})",
            "model": self.model or "—",
            "retention_note": "" if not self.external else "راجع سياسة الاحتفاظ لدى مشغّل الخادم البعيد.",
            "message": "" if self.available() else "غير مضبوط في بيئة الخادم: " + "، ".join(missing),
        }

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> Completion:
        if not self.available():
            raise ProviderUnavailable("خادم النماذج غير مضبوط (العنوان أو اسم النموذج)")
        headers = {"content-type": "application/json"}
        if self.key:
            headers["authorization"] = f"Bearer {self.key}"
        data = _post(f"{self.base}/chat/completions", headers=headers, timeout=self.timeout, who="خادم النماذج",
                     body={"model": self.model, "max_tokens": max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        u = data.get("usage", {})
        return Completion(data["choices"][0]["message"]["content"], u.get("prompt_tokens", 0),
                          u.get("completion_tokens", 0), data.get("model", self.model))


class Metered(Provider):
    """Wraps a provider for one run and counts input and output tokens separately (prices differ)."""

    def __init__(self, inner: Provider) -> None:
        self.inner, self.name, self.external = inner, inner.name, inner.external
        self.input_tokens = self.output_tokens = self.calls = 0

    def available(self) -> bool:
        return self.inner.available()

    def describe(self) -> dict[str, Any]:
        return self.inner.describe()

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> Completion:
        c = self.inner.complete(system, prompt, max_tokens)
        self.calls += 1
        self.input_tokens += c.input_tokens
        self.output_tokens += c.output_tokens
        return c


def get_provider() -> Provider:
    name = get_settings().llm_provider
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openai_compatible":
        return OpenAICompatibleProvider()
    return Provider()


def estimate_cost(input_tokens: int, output_tokens: int) -> float | None:
    try:
        pin = float(os.environ.get("NIS_LLM_PRICE_IN_PER_MTOK", ""))
        pout = float(os.environ.get("NIS_LLM_PRICE_OUT_PER_MTOK", ""))
    except ValueError:
        return None
    return round(input_tokens / 1e6 * pin + output_tokens / 1e6 * pout, 6)


def parse_json_block(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from a model reply; None if absent/invalid (never guessed)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None
