"""NH5MP Discord bot: active players / lobbies = the community server's /stats + SteamNet players.

SteamNet races run over Steam, so the community server can't see them. Every SteamNet game (loader with presence_url set in
H5TrackLoader/steamnet/steamnet_settings.txt) POSTs a small JSON heartbeat to this bot every 30 s while Multiplayer is open:
  {"steam_id": "...", "name": "...", "proto": "5", "state": "menu|lobby|loading|racing|results|spectating|offline",
   "game_id": "...", "is_host": true, "players": 2, "cap": 20, "track": "...", "series": "CUP", "private": false}
(game_id .. private only while in a race). Players heard from in the last 90 s (not "offline") are active; lobbies are the
distinct game_ids among them.

Run: DISCORD_TOKEN=... python nh5mp_bot.py   (listens on $PORT, else $HEARTBEAT_PORT, else 8095)
On Railway: service Settings > Networking > Generate Domain (target port = the service's PORT) gives https://<name>.up.railway.app
Game setting: presence_url = https://<name>.up.railway.app/heartbeat   (check: open https://<name>.up.railway.app/stats)
"""
import json
import os
import time

import discord
import requests
from aiohttp import web
from discord.ext import tasks, commands

intents = discord.Intents.default()
intents.message_content = True  # Required for prefix commands!
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

STATS_API_URL = "http://72.39.41.141:8000/stats"

PLAYERS_VC_ID = 1543832033523146782
LOBBIES_VC_ID = 1546259866207785010

# Railway gives the service's public domain to the port in $PORT (Settings > Networking > Generate Domain)
HEARTBEAT_PORT = int(os.getenv("PORT") or os.getenv("HEARTBEAT_PORT") or "8095")
ACTIVE_SECONDS = 90

# steam_id -> {"t": last heard (time.time()), "state": ..., "game_id": ...}
steamnet_players = {}


def steamnet_counts():
    """(players, lobbies) heard from SteamNet games in the last ACTIVE_SECONDS."""
    now = time.time()
    players = 0
    lobbies = set()
    for sid, p in list(steamnet_players.items()):
        if now - p["t"] > ACTIVE_SECONDS * 4:
            del steamnet_players[sid]  # forget long-gone players
            continue
        if now - p["t"] > ACTIVE_SECONDS or p["state"] == "offline":
            continue
        players += 1
        if p.get("game_id"):
            lobbies.add(p["game_id"])
    return players, len(lobbies)


async def heartbeat(request):
    try:
        data = json.loads(await request.text())
        sid = str(data.get("steam_id", ""))
        if not sid.isdigit() or len(sid) > 20:
            return web.Response(status=400, text="bad steam_id", headers={"ACTUAL-STATUS-CODE": "400"})
        steamnet_players[sid] = {
            "t": time.time(),
            "state": str(data.get("state", "menu"))[:20],
            "game_id": str(data.get("game_id", ""))[:40],
        }
        return web.Response(text="{}", content_type="application/json", headers={"ACTUAL-STATUS-CODE": "200"})
    except Exception as e:
        print(f"Bad heartbeat: {e}")
        return web.Response(status=400, text="bad request", headers={"ACTUAL-STATUS-CODE": "400"})


async def stats(request):
    """The combined numbers, same JSON shape as the community server's /stats (handy for checking)."""
    players, lobbies = get_server_stats()
    return web.json_response({"active_players": players or 0, "active_lobbies": lobbies or 0})


def get_server_stats():
    """Community server /stats + SteamNet heartbeats. Returns (players, lobbies), or (None, None) if nothing could be read."""
    sn_players, sn_lobbies = steamnet_counts()
    try:
        response = requests.get(STATS_API_URL, timeout=10)
        data = response.json()
        players = data.get("active_players", 0)
        lobbies = data.get("active_lobbies", 0)
    except Exception as e:
        print(f"Error fetching Stats API: {e}")
        players, lobbies = 0, 0
    return players + sn_players, lobbies + sn_lobbies


async def update_voice_channel(channel_id, new_name):
    """Helper to safely update a voice channel name."""
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            # Avoid sending unnecessary edit calls if the name hasn't changed
            if channel.name != new_name:
                await channel.edit(name=new_name)
        except discord.HTTPException as e:
            print(f"Failed to update channel {channel_id}: {e}")


# Loop 1: Fast update for Discord presence (Every 30 seconds)
@tasks.loop(seconds=30)
async def update_presence_loop():
    players, lobbies = get_server_stats()
    if players is not None and lobbies is not None:
        activity = discord.Game(name=f"NH5MP: {players} Players | {lobbies} Lobbies")
        await bot.change_presence(activity=activity)


# Loop 2: Slow update for Voice Channels to respect Discord rate limits (Every 10 minutes)
@tasks.loop(minutes=10)
async def update_channels_loop():
    players, lobbies = get_server_stats()
    if players is not None and lobbies is not None:
        await update_voice_channel(PLAYERS_VC_ID, f"🔴 Active Players: {players}")
        await update_voice_channel(LOBBIES_VC_ID, f"🏁 Active Lobbies: {lobbies}")


@update_presence_loop.before_loop
@update_channels_loop.before_loop
async def before_loops():
    await bot.wait_until_ready()


heartbeat_server_started = False


async def start_heartbeat_server():
    global heartbeat_server_started
    if heartbeat_server_started:
        return
    heartbeat_server_started = True
    app = web.Application()
    app.router.add_post("/heartbeat", heartbeat)
    app.router.add_get("/stats", stats)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", HEARTBEAT_PORT).start()
    print(f"SteamNet heartbeats on port {HEARTBEAT_PORT} (POST /heartbeat, GET /stats)")


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    await start_heartbeat_server()

    if not update_presence_loop.is_running():
        update_presence_loop.start()

    if not update_channels_loop.is_running():
        update_channels_loop.start()


bot.run(os.getenv("DISCORD_TOKEN"))
