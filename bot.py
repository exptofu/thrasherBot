import asyncio
import logging
import os
import sqlite3
import time

import aiohttp
import discord
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

EBIRD_KEY = os.environ["EBIRD_API_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
REGION = os.environ.get("EBIRD_REGION", "US-GA")
BACK_DAYS = int(os.environ.get("EBIRD_BACK_DAYS", "14"))
POLL_MINUTES = int(os.environ.get("POLL_MINUTES", "15"))
DB_PATH = os.environ.get("DB_PATH", "sightings.db")
HOTSPOT_REFRESH_SECONDS = 24 * 3600

API = "https://api.ebird.org/v2"
HEADERS = {"x-ebirdapitoken": EBIRD_KEY}

log = logging.getLogger("thrasherbot")

db = sqlite3.connect(DB_PATH)
db.executescript(
    """
    CREATE TABLE IF NOT EXISTS sightings (
        sub_id TEXT NOT NULL,
        species_code TEXT NOT NULL,
        scope TEXT NOT NULL,
        PRIMARY KEY (sub_id, species_code)
    );
    CREATE TABLE IF NOT EXISTS posts (
        species_code TEXT NOT NULL,
        scope TEXT NOT NULL,
        thread_id INTEGER NOT NULL,
        PRIMARY KEY (species_code, scope)
    );
    """
)
db.commit()

hotspots: set[str] = set()
hotspots_loaded_at = 0.0


async def get_json(session: aiohttp.ClientSession, path: str, **params):
    async with session.get(f"{API}{path}", headers=HEADERS, params=params) as r:
        r.raise_for_status()
        return await r.json()


async def refresh_hotspots(session: aiohttp.ClientSession):
    global hotspots, hotspots_loaded_at
    if hotspots and time.time() - hotspots_loaded_at < HOTSPOT_REFRESH_SECONDS:
        return
    data = await get_json(session, f"/ref/hotspot/{REGION}", fmt="json")
    hotspots = {h["locId"] for h in data}
    hotspots_loaded_at = time.time()
    log.info("Loaded %d hotspots", len(hotspots))


def format_sighting(o: dict) -> discord.Embed:
    if o.get("obsReviewed") and o.get("obsValid"):
        status, color = "Confirmed", discord.Color.green()
    elif o.get("obsReviewed"):
        status, color = "Rejected", discord.Color.red()
    else:
        status, color = "Unreviewed", discord.Color.orange()

    embed = discord.Embed(
        title=o["comName"],
        description=f"*{o['sciName']}*",
        url=f"https://ebird.org/checklist/{o['subId']}",
        color=color,
    )
    embed.add_field(name="Count", value=str(o.get("howMany", "X")))
    embed.add_field(name="Date", value=o["obsDt"])
    embed.add_field(name="Status", value=status)
    embed.add_field(
        name="Location",
        value=(
            f"[{o['locName']}](https://ebird.org/hotspot/{o['locId']})"
            if o["locId"] in hotspots
            else o["locName"]
        ),
        inline=False,
    )
    if o.get("subnational2Name"):
        embed.add_field(name="County", value=o["subnational2Name"])
    embed.add_field(
        name="Map",
        value=f"[Open map](https://maps.google.com/?q={o['lat']},{o['lng']})",
    )
    return embed


async def get_thread(client: discord.Client, thread_id: int):
    try:
        ch = client.get_channel(thread_id) or await client.fetch_channel(thread_id)
        return ch if isinstance(ch, discord.Thread) else None
    except discord.NotFound:
        return None


def scope_of(o: dict) -> str:
    if o["locId"] in hotspots:
        return o["locId"]
    return "county:" + o.get("subnational2Code", o.get("subnational2Name", "unknown"))


def post_title(o: dict) -> str:
    county = o.get("subnational2Name", "Unknown")
    prefix = f"[{county}]"
    if o["locId"] in hotspots:
        prefix += f"[{o['locName']}]"
    return f"{prefix} {o['comName']} ({o['obsDt'][:10]})"[:100]


async def post_sighting(
    client: discord.Client, channel: discord.ForumChannel, o: dict, scope: str
):
    embed = format_sighting(o)
    key = (o["speciesCode"], scope)
    row = db.execute(
        "SELECT thread_id FROM posts WHERE species_code=? AND scope=?", key
    ).fetchone()
    thread = await get_thread(client, row[0]) if row else None
    if thread:
        if thread.archived:
            await thread.edit(archived=False)
        await thread.send(embed=embed)
        return

    created = await channel.create_thread(name=post_title(o), embed=embed)
    db.execute("INSERT OR REPLACE INTO posts VALUES (?,?,?)", (*key, created.thread.id))
    db.commit()


@tasks.loop(minutes=POLL_MINUTES)
async def poll():
    channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    try:
        async with aiohttp.ClientSession() as session:
            await refresh_hotspots(session)
            obs = await get_json(
                session,
                f"/data/obs/{REGION}/recent/notable",
                detail="full",
                back=BACK_DAYS,
            )
    except aiohttp.ClientError:
        log.exception("eBird request failed")
        return

    current = {(o["subId"], o["speciesCode"]) for o in obs}
    known = {
        (r[0], r[1]) for r in db.execute("SELECT sub_id, species_code FROM sightings")
    }

    for o in sorted(obs, key=lambda o: o["obsDt"]):
        k = (o["subId"], o["speciesCode"])
        if k in known:
            continue
        scope = scope_of(o)
        try:
            await post_sighting(client, channel, o, scope)
        except discord.HTTPException:
            log.exception("Failed to post %s", k)
            continue
        db.execute("INSERT OR IGNORE INTO sightings VALUES (?,?,?)", (*k, scope))
        db.commit()
        known.add(k)
        await asyncio.sleep(1)

    # Purge records that dropped off the API, and posts with no remaining sightings.
    for sub_id, species in known - current:
        db.execute(
            "DELETE FROM sightings WHERE sub_id=? AND species_code=?", (sub_id, species)
        )
    db.execute(
        """DELETE FROM posts WHERE NOT EXISTS (
               SELECT 1 FROM sightings s
               WHERE s.species_code = posts.species_code AND s.scope = posts.scope)"""
    )
    db.commit()


REQUIRED_PERMS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    send_messages_in_threads=True,
    read_message_history=True,
)


class Bot(discord.Client):
    async def on_ready(self):
        invite = discord.utils.oauth_url(
            self.user.id, permissions=REQUIRED_PERMS, scopes=("bot",)
        )
        try:
            channel = self.get_channel(CHANNEL_ID) or await self.fetch_channel(CHANNEL_ID)
        except (discord.Forbidden, discord.NotFound):
            log.error("Cannot access channel %s. Re-authorize the bot: %s", CHANNEL_ID, invite)
            await self.close()
            return
        if not isinstance(channel, discord.ForumChannel):
            log.error("Channel %s is not a forum channel", CHANNEL_ID)
            await self.close()
            return

        have = channel.permissions_for(channel.guild.me)
        missing = [n for n, v in REQUIRED_PERMS if v and not getattr(have, n)]
        if missing:
            log.error(
                "Missing permissions in #%s: %s. Authorize with: %s",
                channel.name, ", ".join(missing), invite,
            )
            await self.close()
            return

        if not poll.is_running():
            poll.start()


client = Bot(intents=discord.Intents.default())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client.run(DISCORD_TOKEN)
