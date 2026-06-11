"""Poll Railway until the latest Shadow deployment is successful."""

import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
WAIT_SEC = 180
POLL_SEC = 15


def load_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.getenv("RAILWAY_API_TOKEN", "")


def gql(token: str, query: str, variables: dict | None = None) -> dict:
    body: dict = {"query": query}
    if variables:
        body["variables"] = variables
    req = urllib.request.Request(
        "https://backboard.railway.com/graphql/v2",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ShadowSyn/1.0",
        },
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload


def service_id(token: str) -> str:
    data = gql(
        token,
        """
        query ($id: String!) {
          project(id: $id) {
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": PROJECT_ID},
    )
    for edge in data["data"]["project"]["services"]["edges"]:
        if edge["node"]["name"] == SERVICE_NAME:
            return edge["node"]["id"]
    raise RuntimeError("Shadow service not found")


def latest_deployment(token: str, sid: str) -> dict | None:
    data = gql(
        token,
        """
        query ($id: String!) {
          service(id: $id) {
            serviceInstances { edges { node {
              latestDeployment { id status createdAt }
            } } }
          }
        }
        """,
        {"id": sid},
    )
    edges = data["data"]["service"]["serviceInstances"]["edges"]
    if not edges:
        return None
    return edges[0]["node"]["latestDeployment"]


def main():
    token = load_token()
    if not token:
        raise SystemExit("RAILWAY_API_TOKEN missing")
    sid = service_id(token)
    deadline = time.time() + WAIT_SEC
    last = None
    while time.time() < deadline:
        dep = latest_deployment(token, sid)
        if dep:
            status = dep.get("status")
            dep_id = dep.get("id")
            if (dep_id, status) != last:
                print(f"deployment {dep_id}: {status}")
                last = (dep_id, status)
            if status == "SUCCESS":
                print("Railway deploy SUCCESS")
                return
            if status in ("FAILED", "CRASHED"):
                raise SystemExit(f"Railway deploy failed: {status}")
        time.sleep(POLL_SEC)
    print("Timed out waiting for Railway deploy (check dashboard).")


if __name__ == "__main__":
    main()
