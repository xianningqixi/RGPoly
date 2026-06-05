#!/usr/bin/env python3
"""AI decision layer for Polymarket simulation signals.

Default mode is a deterministic local decision model so the simulator is stable
without external API keys. If AI_DECISION_MODE=openai and OPENAI_API_KEY is set,
the engine asks an LLM for the final TAKE/SKIP decision and then applies the
same hard safety vetoes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any


CACHE_PATH = Path("ai_decision_cache.json")
DECISION_FIELDS = [
    "decision_ts",
    "candidate_id",
    "asset",
    "slug",
    "direction",
    "decision",
    "confidence",
    "stake_usdc",
    "reason",
    "risk_flags",
    "expected_edge_bps",
    "would_live_fill",
    "model",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def cache_key(candidate: dict[str, Any]) -> str:
    payload = {
        "asset": candidate.get("asset"),
        "slug": candidate.get("slug"),
        "direction": candidate.get("direction"),
        "bucket": candidate.get("signal_bucket") or candidate.get("candidate_id"),
        "ask": round(fnum(candidate.get("best_ask")), 3),
        "edge": round(fnum(candidate.get("expected_edge_bps")), 0),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def read_cache(path: Path = CACHE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_cache(cache: dict[str, Any], path: Path = CACHE_PATH) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def append_decision(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=DECISION_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in DECISION_FIELDS})


def hard_risk_flags(candidate: dict[str, Any], args: argparse.Namespace) -> list[str]:
    flags: list[str] = []
    if fnum(candidate.get("expected_edge_bps")) < args.min_expected_edge_bps:
        flags.append("edge_too_low")
    if fnum(candidate.get("slippage_bps")) > args.max_slippage_bps:
        flags.append("slippage_too_high")
    if fnum(candidate.get("source_to_ask_gap")) > args.max_source_to_ask_gap:
        flags.append("source_to_ask_gap_too_high")
    if fnum(candidate.get("ask_depth_usdc")) < args.min_ask_depth_usdc:
        flags.append("depth_too_low")
    if str(candidate.get("would_live_fill") or "").upper() not in {"YES", "TRUE", "1"}:
        flags.append("would_not_live_fill")
    if fnum(candidate.get("source_spread_bps")) > args.max_source_spread_bps:
        flags.append("source_disagreement")
    if fnum(candidate.get("seconds_to_end")) < args.min_seconds_before_end:
        flags.append("too_close_to_end")
    return flags


def local_decision(candidate: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    flags = hard_risk_flags(candidate, args)
    edge = fnum(candidate.get("expected_edge_bps"))
    move = abs(fnum(candidate.get("move_bps")))
    depth = fnum(candidate.get("ask_depth_usdc"))
    slippage = fnum(candidate.get("slippage_bps"))
    source_spread = fnum(candidate.get("source_spread_bps"))

    score = 50.0
    score += min(25.0, edge / 4.0)
    score += min(12.0, move / 3.0)
    score += min(8.0, depth / 25.0)
    score -= min(15.0, slippage / 20.0)
    score -= min(10.0, source_spread)
    confidence = max(0.0, min(0.95, score / 100.0))

    decision = "SKIP" if flags else "TAKE"
    if decision == "TAKE" and confidence < args.min_confidence:
        decision = "SKIP"
        flags.append("confidence_too_low")

    stake = min(args.stake_usdc, max(0.0, edge / 100.0)) if decision == "TAKE" else 0.0
    if decision == "TAKE":
        stake = max(args.min_take_stake_usdc, min(args.stake_usdc, stake or args.min_take_stake_usdc))

    reason = (
        f"edge={edge:.1f}bps move={move:.1f}bps depth={depth:.1f}U "
        f"slip={slippage:.1f}bps spread={source_spread:.1f}bps"
    )
    return {
        "decision": decision,
        "confidence": round(confidence, 4),
        "stake_usdc": round(stake, 4),
        "reason": reason,
        "risk_flags": flags,
        "expected_edge_bps": round(edge, 2),
        "model": "local_ai_risk_model_v1",
    }


def openai_decision(candidate: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return local_decision(candidate, args)
    model = os.environ.get("AI_DECISION_OPENAI_MODEL", "gpt-4o-mini")
    prompt = {
        "task": "Decide whether this Polymarket simulation signal should be taken. Return strict JSON only.",
        "schema": {
            "decision": "TAKE or SKIP",
            "confidence": "0.0-1.0",
            "stake_usdc": "number",
            "reason": "short reason",
            "risk_flags": ["strings"],
            "expected_edge_bps": "number",
        },
        "candidate": candidate,
        "rules": {
            "simulation_only": True,
            "do_not_take_if_negative_edge": True,
            "do_not_take_if_depth_or_live_fill_bad": True,
            "max_stake_usdc": args.stake_usdc,
        },
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a conservative trading risk manager for a simulation only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=args.openai_timeout_sec) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        decision = json.loads(content)
    except Exception as exc:
        decision = local_decision(candidate, args)
        decision["risk_flags"] = list(decision.get("risk_flags") or []) + [f"openai_fallback:{type(exc).__name__}"]
        return decision

    flags = hard_risk_flags(candidate, args)
    if flags:
        decision["decision"] = "SKIP"
        merged = list(decision.get("risk_flags") or [])
        decision["risk_flags"] = sorted(set(merged + flags))
    decision["confidence"] = max(0.0, min(1.0, fnum(decision.get("confidence"))))
    decision["stake_usdc"] = min(args.stake_usdc, fnum(decision.get("stake_usdc"))) if decision.get("decision") == "TAKE" else 0.0
    decision["expected_edge_bps"] = fnum(decision.get("expected_edge_bps") or candidate.get("expected_edge_bps"))
    decision["model"] = model
    return decision


def decide(candidate: dict[str, Any], args: argparse.Namespace, *, use_cache: bool = True) -> dict[str, Any]:
    cache = read_cache()
    key = cache_key(candidate)
    if use_cache and key in cache:
        decision = dict(cache[key])
        decision["cached"] = True
    else:
        mode = os.environ.get("AI_DECISION_MODE", "local").lower()
        decision = openai_decision(candidate, args) if mode == "openai" else local_decision(candidate, args)
        cache[key] = decision
        write_cache(cache)
        decision = dict(decision)
        decision["cached"] = False
    return decision


def decision_row(candidate: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_ts": now_iso(),
        "candidate_id": candidate.get("candidate_id"),
        "asset": candidate.get("asset"),
        "slug": candidate.get("slug"),
        "direction": candidate.get("direction"),
        "decision": decision.get("decision"),
        "confidence": decision.get("confidence"),
        "stake_usdc": decision.get("stake_usdc"),
        "reason": decision.get("reason"),
        "risk_flags": ";".join(decision.get("risk_flags") or []),
        "expected_edge_bps": decision.get("expected_edge_bps"),
        "would_live_fill": candidate.get("would_live_fill"),
        "model": decision.get("model"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("crypto_lead_lag_candidates.csv"))
    parser.add_argument("--output", type=Path, default=Path("ai_signal_decisions.csv"))
    parser.add_argument("--stake-usdc", type=float, default=1.0)
    parser.add_argument("--min-take-stake-usdc", type=float, default=1.0)
    parser.add_argument("--min-confidence", type=float, default=0.58)
    parser.add_argument("--min-expected-edge-bps", type=float, default=25.0)
    parser.add_argument("--max-slippage-bps", type=float, default=200.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.015)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=20.0)
    parser.add_argument("--max-source-spread-bps", type=float, default=8.0)
    parser.add_argument("--min-seconds-before-end", type=float, default=35.0)
    parser.add_argument("--openai-timeout-sec", type=float, default=12.0)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.input.exists():
        print("No candidates file.")
        return 0
    with args.input.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    for candidate in rows:
        decision = decide(candidate, args)
        row = decision_row(candidate, decision)
        append_decision(args.output, row)
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
