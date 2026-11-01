"""Anthropic Claude via raw HTTPX — no SDK needed.

Uses the Anthropic Messages REST API directly, keeping full Python 3.15
compatibility while avoiding the SDK's version-gated import overhead.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from ..config import settings

# USD per 1M tokens: (input, output). Used only for the budget ledger.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4":      (15.0, 75.0),
    "claude-sonnet-4-5":  (3.0,  15.0),
    "claude-3-5-sonnet":  (3.0,  15.0),
    "claude-3-5-haiku":   (0.80,  4.0),
    "claude-3-haiku":     (0.25,  1.25),
}

LEDGER_FILE = Path(__file__).resolve().parents[2] / "llm_spend.json"
_ledger_lock = threading.Lock()

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class BudgetExceeded(RuntimeError):
    """The configured LLM budget for the current window is used up."""


def _price(model: str) -> tuple[float, float]:
    for name in sorted(PRICES, key=len, reverse=True):
        if model.startswith(name):
            return PRICES[name]
    return PRICES["claude-sonnet-4-5"]


def _window_start(today: date) -> date:
    start = date.fromisoformat(settings.llm_budget_start)
    days = max(settings.llm_budget_days, 1)
    while today >= start + timedelta(days=days):
        start += timedelta(days=days)
    return start


def spend() -> dict:
    """Current budget window: start, spent, cap, calls."""
    start = _window_start(datetime.now(timezone.utc).date()).isoformat()
    try:
        data = json.loads(LEDGER_FILE.read_text())
    except (OSError, ValueError):
        data = {}
    if data.get("window_start") != start:
        data = {"window_start": start, "spent_usd": 0.0, "calls": 0}
    data["budget_usd"] = settings.llm_budget_usd
    return data


def _record(model: str, input_tokens: int, output_tokens: int) -> None:
    p_in, p_out = _price(model)
    cost = (input_tokens * p_in + output_tokens * p_out) / 1_000_000
    with _ledger_lock:
        data = spend()
        data["spent_usd"] = round(data["spent_usd"] + cost, 6)
        data["calls"] += 1
        try:
            LEDGER_FILE.write_text(json.dumps(data))
        except OSError:
            pass


def _check_budget() -> None:
    cap = settings.llm_budget_usd
    if cap and spend()["spent_usd"] >= cap:
        raise BudgetExceeded(
            f"llm_budget_exceeded: LLM budget of ${cap:.2f} for this window is used up"
        )


def chat(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 1200,
    temperature: float | None = None,
    json_mode: bool = False,
    reasoning_effort: str | None = None,  # kept for API compat, unused
) -> str:
    api_key = (settings.anthropic_api_key or "").strip()
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY in backend/.env. Please configure your Anthropic API key.")

    _check_budget()

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if temperature is not None:
        payload["temperature"] = temperature

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_API_VERSION,
        "content-type": "application/json",
    }

    try:
        resp = httpx.post(
            ANTHROPIC_API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to connect to Anthropic API: {exc}") from exc

    if resp.status_code != 200:
        err_msg = resp.text
        try:
            err_json = resp.json()
            err_msg = err_json.get("error", {}).get("message", err_msg)
        except Exception:
            pass
        raise RuntimeError(f"Anthropic API error ({resp.status_code}): {err_msg}")

    data = resp.json()
    content = data.get("content", [{}])[0].get("text", "")

    usage = data.get("usage", {})
    _record(model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    # Strip markdown fences if json_mode was requested
    if json_mode:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

    return content.strip()
