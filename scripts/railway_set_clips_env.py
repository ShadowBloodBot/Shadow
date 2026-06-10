"""Set clips-related Railway variables and optionally trigger redeploy."""

import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.railway"

PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"

# Hall of Fame: unset keeps locked thread on ingest panel (recommended).
# Set only when a dedicated read-only HOF text channel exists.
CLIPS_HOF_CHANNEL_ID = os.getenv("CLIPS_HOF_CHANNEL_ID", "")

MEDAL_API_KEY = os.getenv("MEDAL_API_KEY", "")


def load_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    token = os.getenv("RAILWAY_API_TOKEN", "")
    if not token:
        raise SystemExit("RAILWAY_API_TOKEN not set (.env.railway or env)")
    return token


def gql(token: str, query: str, variables: dict | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "ShadowSyn-Deploy/1.0",
    }
    body: dict = {"query": query}
    if variables:
        body["variables"] = variables
    req = urllib.request.Request(
        "https://backboard.railway.com/graphql/v2",
        data=json.dumps(body).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload


def resolve_ids(token: str) -> tuple[str, str]:
    data = gql(
        token,
        """
        query ($id: String!) {
          project(id: $id) {
            id
            environments { edges { node { id name } } }
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": PROJECT_ID},
    )
    project = data["data"]["project"]
    env_edges = project["environments"]["edges"]
    prod = next((e["node"] for e in env_edges if e["node"]["name"] == "production"), None)
    if not prod and env_edges:
        prod = env_edges[0]["node"]
    if not prod:
        raise RuntimeError("No Railway environment found")

    service = next(
        (s["node"] for s in project["services"]["edges"] if s["node"]["name"] == SERVICE_NAME),
        None,
    )
    if not service:
        names = [s["node"]["name"] for s in project["services"]["edges"]]
        raise RuntimeError(f"Service {SERVICE_NAME!r} not found. Available: {names}")

    return prod["id"], service["id"]


def upsert_var(token: str, env_id: str, service_id: str, name: str, value: str, skip_deploys: bool):
    gql(
        token,
        """
        mutation ($input: VariableUpsertInput!) {
          variableUpsert(input: $input)
        }
        """,
        {
            "input": {
                "projectId": PROJECT_ID,
                "environmentId": env_id,
                "serviceId": service_id,
                "name": name,
                "value": value,
                "skipDeploys": skip_deploys,
            }
        },
    )
    print(f"  set {name}={'(empty)' if not value else '(set)'}")


def fetch_medal_public_key() -> str:
    """Medal public-use keys are safe for server-side metadata resolution."""
    import urllib.error

    req = urllib.request.Request(
        "https://developers.medal.tv/v1/generate_public_key",
        headers={"User-Agent": "ShadowSyn/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:300]
        raise RuntimeError(f"Medal key generation failed ({e.code}): {err_body}") from e

    if body.startswith("{"):
        data = json.loads(body)
        key = data.get("apiKey") or data.get("key") or data.get("publicKey") or ""
    else:
        m = re.search(r"(pub_[A-Za-z0-9]+)", body)
        key = m.group(1) if m else ""
    if not key:
        raise RuntimeError(f"Unexpected Medal key response: {body[:200]}")
    return key


def get_existing_var(token: str, env_id: str, service_id: str, name: str) -> str:
    data = gql(
        token,
        """
        query ($projectId: String!, $environmentId: String!, $serviceId: String!) {
          variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
        }
        """,
        {
            "projectId": PROJECT_ID,
            "environmentId": env_id,
            "serviceId": service_id,
        },
    )
    variables = data.get("data", {}).get("variables") or {}
    return variables.get(name, "") if isinstance(variables, dict) else ""


def main():
    token = load_token()
    env_id, service_id = resolve_ids(token)
    print(f"Railway project={PROJECT_ID} env={env_id} service={service_id}")

    medal_key = MEDAL_API_KEY or get_existing_var(token, env_id, service_id, "MEDAL_API_KEY")
    if not medal_key:
        try:
            print("Generating Medal public API key...")
            medal_key = fetch_medal_public_key()
        except Exception as e:
            print(f"  Medal key unavailable ({e}). Metadata will use HTML scrape fallback.")
            print("  Add MEDAL_API_KEY manually in Railway after generating at https://medal.tv/settings/developers")

    # Set vars before git push deploy; skipDeploys so push triggers a single deploy.
    if medal_key:
        upsert_var(token, env_id, service_id, "MEDAL_API_KEY", medal_key, skip_deploys=True)
    if CLIPS_HOF_CHANNEL_ID:
        upsert_var(token, env_id, service_id, "CLIPS_HOF_CHANNEL_ID", CLIPS_HOF_CHANNEL_ID, skip_deploys=True)
    else:
        print("  CLIPS_HOF_CHANNEL_ID unset — Hall of Fame uses locked thread on ingest panel.")

    print("Railway clips env vars applied.")


if __name__ == "__main__":
    main()
