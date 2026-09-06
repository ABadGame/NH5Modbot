import os
import requests
import discord
from discord.ext import tasks, commands

intents = discord.Intents.default()
intents.message_content = True  # Required for prefix commands!
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

STATS_API_URL = "http://72.39.41.141:8000/stats"

# Replace these with your actual Voice Channel IDs
PLAYERS_VC_ID = 1543832033523146782
LOBBIES_VC_ID = 1546259866207785010


def get_server_stats():
    """Fetches stats from the API and returns a tuple (players, lobbies)."""
    try:
        response = requests.get(STATS_API_URL, timeout=10)
        data = response.json()
        
        players = data.get("active_players", 0)
        lobbies = data.get("active_lobbies", 0)
        
        return players, lobbies
    except Exception as e:
        print(f"Error fetching Stats API: {e}")
        return None, None


async def update_voice_channel(channel_id, new_name):
    """Helper to safely update a voice channel name."""
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            await channel.edit(name=new_name)
        except discord.HTTPException as e:
            print(f"Failed to update channel {channel_id}: {e}")


async def process_stats(players, lobbies):
    """Core logic to update status presence and both voice channels."""
    # Update Bot Status
    activity = discord.Game(name=f"NH5MP: {players} Players | {lobbies} Lobbies")
    await bot.change_presence(activity=activity)

    # Update Voice Channels
    await update_voice_channel(PLAYERS_VC_ID, f"🔴 NH5 Players: {players}")
    await update_voice_channel(LOBBIES_VC_ID, f"🏁 NH5 Lobbies: {lobbies}")


@tasks.loop(minutes=10)
async def update_stats_loop():
    players, lobbies = get_server_stats()
    if players is not None and lobbies is not None:
        await process_stats(players, lobbies)


@update_stats_loop.before_loop
async def before_update_stats():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    if not update_stats_loop.is_running():
        update_stats_loop.start()


bot.run(os.getenv("DISCORD_TOKEN"))
