import os
import requests
import discord
from discord.ext import tasks, commands

intents = discord.Intents.default()
intents.message_content = True  # Required for prefix commands!
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

STATS_API_URL = "http://72.39.41.141:8000/stats"
VOICE_CHANNEL_ID = 1543832033523146782


def get_server_player_count():
    try:
        response = requests.get(STATS_API_URL, timeout=10)
        data = response.json()
        return data.get("active_players", 0)
    except Exception as e:
        print(f"Error fetching Stats API: {e}")
        return None


async def process_player_count(count):
    """Core logic to update presence and voice channel name."""
    activity = discord.Game(name=f"NASCAR Heat 5 ({count} online)")
    await bot.change_presence(activity=activity)

    vc_channel = bot.get_channel(VOICE_CHANNEL_ID)
    if vc_channel:
        try:
            await vc_channel.edit(name=f"🔴 NH5 Online: {count}")
        except discord.HTTPException as e:
            print(f"Failed to update voice channel name: {e}")


@tasks.loop(minutes=10)
async def update_player_count_loop():
    count = get_server_player_count()
    if count is not None:
        await process_player_count(count)


@update_player_count_loop.before_loop
async def before_update_player_count():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    if not update_player_count_loop.is_running():
        update_player_count_loop.start()


bot.run(os.getenv("DISCORD_TOKEN"))
