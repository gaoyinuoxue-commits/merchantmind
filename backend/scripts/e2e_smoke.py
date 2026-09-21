"""End-to-end smoke test against a running stack (local or Docker).

Exercises the full Observe -> Think -> Act -> Observe Again loop plus the
evaluation / badcase / monitoring layers over real HTTP.

Usage:
    python scripts/e2e_smoke.py [base_url] [merchant_id]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def call(method: str, base: str, path: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail[:500]}") from exc


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    merchant_id = sys.argv[2] if len(sys.argv) > 2 else "M001"
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append((name, condition, detail))
        print(f"[{'PASS' if condition else 'FAIL'}] {name} {detail}")

    status, health = call("GET", base, "/api/health")
    check("health ok", health["status"] == "ok" and health["database"]["status"] == "up",
          f"pgvector={health['database']['pgvector']}")

    _, merchants = call("GET", base, "/api/merchants")
    check("merchant directory seeded", len(merchants["items"]) >= 3, f"n={len(merchants['items'])}")

    _, run = call(
        "POST", base, "/api/agent/run",
        {"merchant_id": merchant_id, "message": "为什么最近 ROI 一直下滑，帮我诊断"},
    )
    check(
        "diagnosis produced",
        bool(run.get("diagnosis") and run["diagnosis"].get("primary_cause")),
        f"intent={run['intent']['intent']} actions={len(run['actions'])}",
    )
    check("trace recorded", bool(run.get("trace_id")), run.get("trace_id", ""))
    check("SYNTHETIC label", run.get("label") == "SYNTHETIC")

    direct_action = next((action for action in run["actions"] if not action["requires_confirmation"]), None)
    if direct_action is not None:
        _, effect = call(
            "POST", base, "/api/agent/act",
            {"merchant_id": merchant_id, "action": direct_action, "confirmed": False, "observe_days": 7},
        )
        check("action executed + observed", effect.get("status") == "executed", str(effect.get("effect_summary"))[:120])
    else:
        check("action executed + observed", False, "no direct action proposed")

    _, evaluation = call("POST", base, "/api/eval/runs?judge=rule")
    metrics = evaluation["metrics"]
    check(
        "eval 54 cases all pass / zero hallucination",
        metrics["total"] == 54 and metrics["passed"] == 54 and metrics["hallucination_rate"] == 0.0,
        f"passed={metrics['passed']}/{metrics['total']} hallu={metrics['hallucination_rate']}",
    )

    call("POST", base, "/api/feedback", {"rating": 2, "comment": "E2E 负反馈冒烟", "merchant_id": merchant_id})
    _, badcases = call("GET", base, "/api/badcases?status=open")
    check("negative feedback auto-opens badcase", len(badcases["items"]) >= 1,
          f"open={len(badcases['items'])}")

    _, overview = call("GET", base, "/api/monitoring/overview")
    check(
        "monitoring three layers labeled",
        overview["monitoring"]["label"] == "Demo/Simulation Metrics"
        and overview["business_kpi"]["label"] == "Synthetic Business Metrics",
        f"requests={overview['monitoring']['requests']} feedback={overview['monitoring']['feedback_count']}",
    )
    check("business KPI window computed", overview["business_kpi"]["anchor_date"] is not None,
          f"roi={overview['business_kpi']['roi']}")

    _, traces = call("GET", base, "/api/traces?limit=5")
    check("trace list available", len(traces["items"]) >= 1, f"n={len(traces['items'])}")

    failed = [name for name, ok, _ in checks if not ok]
    print(f"\nE2E result: {len(checks) - len(failed)}/{len(checks)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
