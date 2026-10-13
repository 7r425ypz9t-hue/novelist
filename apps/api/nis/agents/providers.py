"""Model provider adapter (NFR10, FR25). Swapping providers never touches domain logic.

The default provider is `disabled`: the studio is fully usable for writing, bible, continuity, research and
deterministic analysis without any model. No price table is hard-coded: cost is only estimated when the
operator supplies prices via env (NIS_LLM_PRICE_IN_PER_MTOK / NIS_LLM_PRICE_OUT_PER_MTOK).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings


class ProviderUnavailable(Exception):
    pass


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
        self.model = s.llm_model or "claude-sonnet-5-5"
        self.timeout = s.llm_timeout_s

    def available(self) -> bool:
        return bool(self.key)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "available": self.available(), "external": True,
            "destination": "api.anthropic.com (خدمة خارجية)", "model": self.model,
            "retention_note": "سياسة الاحتفاظ والتدريب لدى المزود يجب مراجعتها في شروطه؛ النظام لا يفترضها.",
            "message": "يُرسل نص المخطوط إلى خدمة خارجية فقط بعد موافقة صريحة على مستوى المشروع والتشغيل."
            if self.available() else "المفتاح غير مضبوط في بيئة الخادم (NIS_LLM_API_KEY).",
        }

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> Completion:
        if not self.available():
            raise ProviderUnavailable("مفتاح المزود غير مضبوط")
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=self.timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"تعذر الاتصال بالمزود: {type(e).__name__}") from e
        data = r.json()
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
        self.model = s.llm_model or "local-model"
        self.timeout = s.llm_timeout_s
        host = urlparse(self.base).hostname or ""
        self.external = host not in ("localhost", "127.0.0.1", "::1", "") and not host.endswith(".local")

    def available(self) -> bool:
        return bool(self.base)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name, "available": self.available(), "external": self.external,
            "destination": f"{self.base} ({'خارجي' if self.external else 'محلي على هذا الجهاز/الشبكة'})",
            "model": self.model,
            "retention_note": "" if not self.external else "راجع سياسة الاحتفاظ لدى مشغّل الخادم البعيد.",
            "message": "" if self.available() else "عنوان الخادم غير مضبوط (NIS_LLM_BASE_URL).",
        }

    def complete(self, system: str, prompt: str, max_tokens: int = 2000) -> Completion:
        if not self.available():
            raise ProviderUnavailable("عنوان الخادم غير مضبوط")
        headers = {"content-type": "application/json"}
        if self.key:
            headers["authorization"] = f"Bearer {self.key}"
        try:
            r = httpx.post(f"{self.base}/chat/completions", headers=headers, timeout=self.timeout, json={
                "model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            })
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"تعذر الاتصال بالخادم: {type(e).__name__}") from e
        data = r.json()
        u = data.get("usage", {})
        return Completion(data["choices"][0]["message"]["content"], u.get("prompt_tokens", 0),
                          u.get("completion_tokens", 0), data.get("model", self.model))


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
