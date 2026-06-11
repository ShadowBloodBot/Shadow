"""Check if /sand is registered on ShadowSyn guild."""

import asyncio
import json
import os
import urllib.request
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
GUILD = "908659586536468540"


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
            "User-Agent": "ShadowSyn/1.0",
        },
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload


def get_discord_token() -> str:
    rt = os.getenv("RAILWAY_API_TOKEN", "")
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                rt = line.split("=", 1)[1].strip()
    env_data = railway_gql(
        rt,
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
    project = env_data["data"]["project"]
    env_id = next(
        e["node"]["id"]
        for e in project["environments"]["edges"]
        if e["node"]["name"] == "production"
    )
    service_id = next(
        s["node"]["id"]
        for s in project["services"]["edges"]
        if s["node"]["name"] == "Shadow"
    )
    vars_data = railway_gql(
        rt,
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
    token = vars_data["data"]["variables"].get("DISCORD_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not in Railway variables")
    return token


async def main():
    discord_token = get_discord_token()
    headers = {"Authorization": f"Bot {discord_token}"}

    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            me = await resp.json()
            print(f"Bot: {me.get('username')} ({me.get('id')}) status={resp.status}")

        app_id = me["id"]
        url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{GUILD}/commands"
        async with session.get(url, headers=headers) as resp:
            cmds = await resp.json()

        if not isinstance(cmds, list):
            print("Error:", cmds)
            return

        names = sorted(c.get("name") for c in cmds)
        print(f"Total guild commands: {len(names)}")
        sand = next((c for c in cmds if c.get("name") == "sand"), None)
        print(f"/sand registered: {sand is not None}")
        if sand:
            subs = [o.get("name") for o in sand.get("options", [])]
            print(f"  subcommands: {subs}")
        else:
            print("Sample commands:", names[:20])
            steam = [c for c in cmds if c.get("name") == "steam"]
            print(f"/steam registered: {bool(steam)}")


if __name__ == "__main__":
    asyncio.run(main())
