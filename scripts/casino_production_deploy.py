"""Trigger Railway redeploy for Shadow and verify casino slash commands on production bot."""

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
GUILD = "908659586536468540"
NEEDED = {"gamble", "redemptions", "give_coins"}
REMOVED = {"claim", "buyin", "shop", "wallet", "duel", "give_scoins"}
WAIT_SEC = 240
POLL_SEC = 15


def load_railway_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    token = os.getenv("RAILWAY_API_TOKEN", "")
    if not token:
        raise SystemExit("RAILWAY_API_TOKEN missing")
    return token


def railway_gql(token: str, query: str, variables: dict | None = None) -> dict:
    body: dict = {"query": query}
    if variables:
        body["variables"] = variables
    req = urllib.request.Request(
        "https://backboard.railway.com/graphql/v2",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ShadowSyn-Deploy/1.0",
        },
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload


def resolve_ids(token: str) -> tuple[str, str]:
    data = railway_gql(
        token,
        """
        query ($id: String!) {
          project(id: $id) {
            environments { edges { node { id name } } }
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": PROJECT_ID},
    )
    project = data["data"]["project"]
    env_id = next(
        e["node"]["id"]
        for e in project["environments"]["edges"]
        if e["node"]["name"] == "production"
    )
    svc_id = next(
        s["node"]["id"]
        for s in project["services"]["edges"]
        if s["node"]["name"] == SERVICE_NAME
    )
    return env_id, svc_id


def fetch_discord_token(token: str, env_id: str, svc_id: str) -> str:
    data = railway_gql(
        token,
        """
        query ($projectId: String!, $environmentId: String!, $serviceId: String!) {
          variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
        }
        """,
        {
            "projectId": PROJECT_ID,
            "environmentId": env_id,
            "serviceId": svc_id,
        },
    )
    variables = data["data"]["variables"]
    discord_token = variables.get("DISCORD_TOKEN") or variables.get("discord_token")
    if not discord_token:
        raise RuntimeError("DISCORD_TOKEN not found in Railway variables")
    return discord_token


def trigger_redeploy(token: str, env_id: str, svc_id: str) -> str:
    data = railway_gql(
        token,
        """
        mutation ($serviceId: String!, $environmentId: String!) {
          serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """,
        {"serviceId": svc_id, "environmentId": env_id},
    )
    return data["data"]["serviceInstanceDeploy"]


def latest_deployment(token: str, svc_id: str) -> dict | None:
    data = railway_gql(
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
        {"id": svc_id},
    )
    edges = data["data"]["service"]["serviceInstances"]["edges"]
    if not edges:
        return None
    return edges[0]["node"]["latestDeployment"]


async def verify_commands(discord_token: str) -> bool:
    headers = {"Authorization": f"Bot {discord_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            me = await resp.json()
            if resp.status != 200:
                print(f"Bot check failed: {resp.status} {me}")
                return False
            print(f"Production bot: {me.get('username')} ({me.get('id')})")

        app_id = me["id"]
        async with session.get(
            f"https://discord.com/api/v10/applications/{app_id}/guilds/{GUILD}/commands",
            headers=headers,
        ) as resp:
            cmds = await resp.json()
        if not isinstance(cmds, list):
            print(f"Command fetch failed: {cmds}")
            return False

        names = {c["name"] for c in cmds}
        found = sorted(names & NEEDED)
        missing = sorted(NEEDED - names)
        stale = sorted(REMOVED & names)
        print(f"Casino commands ({len(found)}/{len(NEEDED)}): {found}")
        if stale:
            print(f"Legacy commands still registered (will clear after sync): {stale}")
        if missing:
            print(f"Missing: {missing}")
            return False
        gamble = next(c for c in cmds if c["name"] == "gamble")
        print(f"/gamble description: {gamble.get('description')}")
        print("VERIFY_OK")
        return True


def main() -> int:
    railway = load_railway_token()
    env_id, svc_id = resolve_ids(railway)
    dep_id = trigger_redeploy(railway, env_id, svc_id)
    print(f"Railway redeploy triggered: {dep_id}")

    discord_token = fetch_discord_token(railway, env_id, svc_id)
    deadline = time.time() + WAIT_SEC
    last = None
    while time.time() < deadline:
        dep = latest_deployment(railway, svc_id)
        if dep:
            status = dep.get("status")
            dep_key = (dep.get("id"), status)
            if dep_key != last:
                print(f"deployment {dep.get('id')}: {status}")
                last = dep_key
            if status == "SUCCESS":
                break
            if status in ("FAILED", "CRASHED"):
                print(f"Railway deploy failed: {status}")
                return 1
        time.sleep(POLL_SEC)
    else:
        print("Deploy wait timed out — verifying commands anyway.")

    ok = asyncio.run(verify_commands(discord_token))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
