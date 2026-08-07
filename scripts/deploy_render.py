"""Deploy SwingScore to Render using the public API.

Usage:
  $env:RENDER_API_KEY = "rnd_xxx"
  python scripts/deploy_render.py --watch

Steps:
  1. GET  /v1/owners          -> workspace id
  2. POST /v1/services        -> create the web service (free plan)
  3. GET  /v1/deploys/{id}    -> poll until live/failed (with --watch)

Requirements:
  - A Render account already exists.
  - Render's GitHub app must be connected to the account (the "Continue with
    GitHub" signup does this automatically) so Render can access the repo.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.render.com/v1"
REPO = "https://github.com/ddjdanielalves-gif/SwingScore"

SERVICE_PAYLOAD = {
    "type": "web_service",
    "name": "swingscore",
    "repo": REPO,
    "branch": "main",
    "autoDeploy": "yes",
    "envVars": [
        {"key": "SWING_LLM_ENABLED", "value": "false"},
        {"key": "SWING_MOCK_MODE", "value": "false"},
        {"key": "SWING_CACHE_TTL_SECONDS", "value": "3600"},
    ],
    "serviceDetails": {
        "runtime": "python",
        "plan": "free",
        "region": "virginia",
        "numInstances": 1,
        "healthCheckPath": "/health",
        "envSpecificDetails": {
            "buildCommand": "pip install -r backend/requirements.txt",
            "startCommand": "cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT",
        },
    },
}


def _api_key() -> str:
    key = os.environ.get("RENDER_API_KEY", "").strip()
    if not key:
        sys.exit("RENDER_API_KEY not set. Create it at dashboard.render.com -> Settings -> API Keys")
    return key


def _request(method: str, path: str, key: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        try:
            body_out = json.loads(raw)
        except json.JSONDecodeError:
            body_out = {"raw": raw[:500]}
        return exc.code, body_out


def main() -> None:
    key = _api_key()
    watch = "--watch" in sys.argv

    status, owners = _request("GET", "/owners", key)
    if status != 200 or not owners:
        sys.exit(f"Failed to list owners ({status}): {json.dumps(owners, ensure_ascii=False)}")
    owner = owners[0]
    print(f"Workspace: {owner.get('name')} ({owner.get('id')})")

    status, created = _request(
        "POST", "/services", key, {**SERVICE_PAYLOAD, "ownerId": owner["id"]}
    )
    if status != 201:
        sys.exit(f"Failed to create service ({status}): {json.dumps(created, ensure_ascii=False)}")

    service = created.get("service", {})
    deploy_id = created.get("deployId", "")
    print(f"Service created: {service.get('name')} (id {service.get('id')})")
    print(f"Dashboard: {service.get('dashboardUrl')}")
    print(f"Service URL: {service.get('serviceDetails', {}).get('url', '(provisioning...)')}")
    if not deploy_id:
        return

    if not watch:
        print(f"Deploy started: deploy id {deploy_id} (run with --watch to track status)")
        return

    print("Tracking deploy (this can take a few minutes on the free plan)...")
    last = None
    while True:
        time.sleep(15)
        status, deploy = _request("GET", f"/deploys/{deploy_id}", key)
        if status != 200:
            print(f"  (deploy query failed {status})")
            continue
        state = deploy.get("status", "unknown")
        if state != last:
            print(f"  status: {state}")
            last = state
        if state in ("live", "failed", "canceled"):
            print(f"Final status: {state}")
            print(f"Dashboard: {service.get('dashboardUrl')}")
            print(f"URL: {deploy.get('service', {}).get('serviceDetails', {}).get('url', '(check dashboard)')}")
            sys.exit(0 if state == "live" else 1)


if __name__ == "__main__":
    main()
