import asyncio
import json
import logging
import os
import sqlite3

import aiohttp
import discord
from discord.ext import tasks
from dotenv import load_dotenv
from utils.region_channels import ensure_region_forums, ensure_region_tags

load_dotenv()

EBIRD_KEY = os.environ["EBIRD_API_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
REGION = os.environ.get("EBIRD_REGION", "US-GA")
BACK_DAYS = int(os.environ.get("EBIRD_BACK_DAYS", "14"))
POLL_MINUTES = int(os.environ.get("POLL_MINUTES", "15"))
DB_PATH = os.environ.get("DB_PATH", "sightings.db")
REQUEST_DELAY_SECONDS = float(os.environ.get("REQUEST_DELAY_SECONDS", "3"))
DISCORD_CHANNEL_MOVE_DELAY_SECONDS = float(
    os.environ.get("DISCORD_CHANNEL_MOVE_DELAY_SECONDS", "1")
)
MAX_RETRIES = 5
SCHEMA_VERSION = 2

API = "https://api.ebird.org/v2"
HEADERS = {"x-ebirdapitoken": EBIRD_KEY}

log = logging.getLogger("thrasherbot")

# Region slug -> eBird county names. Slugs are the forum tag and discussion forum names.
REGIONS = {
    "dekalb": ["DeKalb"],
    "cobb": ["Cobb"],
    "fulton": ["Fulton"],
    "gwinnett": ["Gwinnett"],
    "cherokee": ["Cherokee"],
    "glynn": ["Glynn"],
    "columbus-fall-line": ["Muscogee", "Harris", "Chattahoochee", "Marion", "Talbot", "Taylor"],
    "athens-metro": ["Clarke", "Oconee", "Oglethorpe"],
    "augusta-metro": ["Richmond", "Columbia"],
    "macon-expanded": [
        "Bibb", "Houston", "Jones", "Peach", "Crawford", "Twiggs", "Wilkinson", "Monroe",
        "Baldwin", "Macon",
    ],
    "chatham-effingham": ["Chatham", "Effingham"],
    "colonial-coast": ["McIntosh", "Camden", "Bryan", "Liberty"],
    "north-georgia": [
        "Rabun", "Habersham", "Lumpkin", "Fannin", "Union", "Towns", "White", "Dawson",
        "Gilmer", "Pickens", "Floyd", "Bartow", "Whitfield", "Catoosa", "Gordon", "Chattooga",
        "Dade", "Walker", "Polk", "Murray",
    ],
    "upper-piedmont": [
        "Hall", "Forsyth", "Barrow", "Jackson", "Madison", "Franklin", "Banks", "Hart",
        "Elbert", "Stephens",
    ],
    "west-central": ["Coweta", "Carroll", "Paulding", "Haralson", "Douglas", "Heard", "Troup", "Meriwether"],
    "south-atlanta": [
        "Clayton", "Fayette", "Henry", "Rockdale", "Newton", "Walton", "Morgan", "Greene",
        "Putnam", "Jasper", "Spalding", "Butts", "Lamar", "Pike", "Upson",
    ],
    "early-wiregrass": [
        "Early", "Decatur", "Thomas", "Sumter", "Dougherty", "Lee", "Worth", "Terrell",
        "Schley", "Webster", "Stewart", "Quitman", "Randolph", "Clay", "Calhoun", "Seminole",
        "Miller", "Baker", "Grady", "Mitchell", "Crisp", "Dooly", "Wilcox", "Turner", "Tift",
        "Brooks", "Cook", "Lowndes", "Berrien", "Colquitt", "Lanier",
    ],
    "west-sandhills": [
        "Laurens", "Washington", "Hancock", "Warren", "Taliaferro", "Glascock", "Jefferson",
        "Johnson", "Emanuel", "Bleckley", "Dodge", "Pulaski", "Telfair", "Wheeler", "Ben Hill",
        "Irwin",
    ],
    "east-sandhills": [
        "Charlton", "Bulloch", "Ware", "Pierce", "Brantley", "Clinch", "Atkinson", "Coffee",
        "Jeff Davis", "Appling", "Bacon", "Treutlen", "Montgomery", "Toombs", "Candler",
        "Jenkins", "Screven", "Tattnall", "Evans", "Long", "Wayne", "Echols",
    ],
    "upper-savannah": ["Burke", "McDuffie", "Lincoln", "Wilkes"],
}
# Region slugs -> geographic categories for discussion and banter channels.
REGION_GROUPS = {
    "Metro Atlanta": ["dekalb", "fulton", "cobb", "gwinnett", "cherokee"],
    "North Georgia": ["north-georgia"],
    "Northeast Georgia": ["upper-piedmont", "athens-metro"],
    "West Georgia": ["columbus-fall-line", "west-central"],
    "Central Georgia": ["macon-expanded", "south-atlanta", "west-sandhills"],
    "East Georgia": ["augusta-metro", "east-sandhills", "upper-savannah"],
    "South Georgia": ["early-wiregrass"],
    "Coastal Georgia": ["glynn", "chatham-effingham", "colonial-coast"],
}
COUNTY_REGION = {c.lower(): r for r, counties in REGIONS.items() for c in counties}
rba_threads: dict[str, int] = {}


def region_of(o: dict) -> str | None:
    name = o.get("subnational2Name", "").lower().removesuffix(" county")
    return COUNTY_REGION.get(name)

db = sqlite3.connect(DB_PATH)
if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
    db.executescript("DROP TABLE IF EXISTS sightings; DROP TABLE IF EXISTS posts;")
db.executescript(
    f"""
    CREATE TABLE IF NOT EXISTS sightings (
        sub_id TEXT NOT NULL,
        species_code TEXT NOT NULL,
        checklist_id TEXT NOT NULL,
        scope TEXT NOT NULL,
        data TEXT NOT NULL,
        PRIMARY KEY (sub_id, species_code)
    );
    -- One forum post per species per hotspot/county.
    CREATE TABLE IF NOT EXISTS posts (
        species_code TEXT NOT NULL,
        scope TEXT NOT NULL,
        thread_id INTEGER NOT NULL,
        PRIMARY KEY (species_code, scope)
    );
    -- One message per species per (shared) checklist.
    CREATE TABLE IF NOT EXISTS groups (
        species_code TEXT NOT NULL,
        checklist_id TEXT NOT NULL,
        scope TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        PRIMARY KEY (species_code, checklist_id)
    );
    PRAGMA user_version = {SCHEMA_VERSION};
    """
)
db.commit()

async def get_json(session: aiohttp.ClientSession, path: str, **params):
    for attempt in range(MAX_RETRIES):
        async with session.get(f"{API}{path}", headers=HEADERS, params=params) as r:
            if r.status == 429 and attempt < MAX_RETRIES - 1:
                wait = int(r.headers.get("Retry-After", 0)) or 30 * 2**attempt
                log.warning("Rate limited on %s; waiting %ss", path, wait)
            else:
                r.raise_for_status()
                return await r.json()
        await asyncio.sleep(wait)


def sub_num(sub_id: str) -> int:
    return int(sub_id.lstrip("S"))


def field_text(text: str) -> str:
    return text if len(text) <= 1024 else text[:1021] + "..."


def is_hotspot(o: dict) -> bool:
    return o.get("locationPrivate") is False


def format_comments(members: list[dict], field: str, unknown_name: str) -> str:
    grouped: dict[str, tuple[str, list[str]]] = {}
    for member in members:
        comment = member.get(field)
        if not comment:
            continue
        normalized = " ".join(comment.split())
        if not normalized:
            continue
        if normalized not in grouped:
            grouped[normalized] = (comment.strip(), [])
        names = grouped[normalized][1]
        name = member.get("userDisplayName", unknown_name)
        if name not in names:
            names.append(name)

    if not grouped:
        return ""
    if len(grouped) == 1:
        return next(iter(grouped.values()))[0]
    return "\n".join(
        f"{names[0]}{' et al.' if len(names) > 1 else ''}: {comment}"
        for comment, names in grouped.values()
    )


def format_sighting(members: list[dict]) -> discord.Embed:
    """Build one embed from every observer's record of the same checklist."""
    members = sorted(members, key=lambda m: sub_num(m["subId"]))
    o = members[0]
    if o.get("obsReviewed") and o.get("obsValid"):
        status, color = "✅ Confirmed", discord.Color.green()
    elif o.get("obsReviewed"):
        status, color = "❌ Rejected", discord.Color.red()
    else:
        status, color = "❓ Unreviewed", discord.Color.orange()

    author = o.get("userDisplayName", "Unknown")
    others = len(members) - 1
    if others:
        author += f" + {others} other{'s' if others > 1 else ''}"

    embed = discord.Embed(
        title=o["comName"],
        description=(
            f"*{o['sciName']}*\n"
            f"[View checklist](https://ebird.org/checklist/{o['subId']})\n"
            f"Observer: {author}"
        ),
        color=color,
    )

    embed.add_field(name="Count", value=str(o.get("howMany", "X")))
    embed.add_field(name="Date", value=o["obsDt"])
    embed.add_field(name="Status", value=status)
    embed.add_field(
        name="Location",
        value=(
            f"[{o['locName']}](https://ebird.org/hotspot/{o['locId']})"
            if is_hotspot(o)
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

    checklist_comment = format_comments(members, "subComments", "Unknown")
    if checklist_comment:
        embed.add_field(
            name="Checklist comments", value=field_text(checklist_comment), inline=False
        )
    obs_comment_text = format_comments(members, "obsComments", "?")
    if obs_comment_text:
        embed.add_field(
            name="Observation comments", value=field_text(obs_comment_text), inline=False
        )
    return embed


async def get_thread(client: discord.Client, thread_id: int):
    try:
        ch = client.get_channel(thread_id) or await client.fetch_channel(thread_id)
        return ch if isinstance(ch, discord.Thread) else None
    except discord.NotFound:
        return None


def scope_of(o: dict) -> str:
    if is_hotspot(o):
        return o["locId"]
    return "county:" + o.get("subnational2Code", o.get("subnational2Name", "unknown"))


async def get_rba_thread(channel: discord.ForumChannel, region: str):
    """Find or create the <region>_rba post in the region's discussion forum."""
    forum = discord.utils.get(channel.guild.forums, name=region)
    if not forum:
        log.warning("No forum channel named %s; skipping RBA message", region)
        return None
    name = f"{region}_rba"
    thread = await get_thread(client, rba_threads[region]) if region in rba_threads else None
    if not thread:
        thread = discord.utils.get(forum.threads, name=name)
    if not thread:
        async for t in forum.archived_threads(limit=None):
            if t.name == name:
                thread = t
                break
    if not thread:
        thread = (
            await forum.create_thread(name=name, content="New sightings for this region.")
        ).thread
    rba_threads[region] = thread.id
    return thread


async def notify_rba(channel: discord.ForumChannel, region: str, post: discord.Thread, o: dict):
    try:
        rba = await get_rba_thread(channel, region)
        if not rba:
            return
        if rba.archived:
            await rba.edit(archived=False)
        await rba.send(
            f"New: [{o['comName']}]({post.jump_url}) - {o.get('subnational2Name', 'Unknown')} "
            f"County, {o['locName']} ({o['obsDt'][:10]})"
        )
    except discord.HTTPException:
        log.exception("Failed to post RBA message for %s", region)


def post_title(o: dict) -> str:
    county = o.get("subnational2Name", "Unknown")
    title = f"[{county}] {o['comName']} ({o['obsDt'][:10]})"
    if is_hotspot(o):
        title += f" @ {o['locName']}"
    return title[:100]


async def send_group(
    client: discord.Client,
    channel: discord.ForumChannel,
    species: str,
    checklist_id: str,
    scope: str,
    members: list[dict],
):
    """Post a new message for the checklist group, or edit its existing one."""
    embed = format_sighting(members)

    existing = db.execute(
        "SELECT message_id FROM groups WHERE species_code=? AND checklist_id=?",
        (species, checklist_id),
    ).fetchone()
    row = db.execute(
        "SELECT thread_id FROM posts WHERE species_code=? AND scope=?", (species, scope)
    ).fetchone()
    thread = await get_thread(client, row[0]) if row else None

    if thread and existing:
        try:
            msg = await thread.fetch_message(existing[0])
            await msg.edit(embed=embed)
            return
        except discord.NotFound:
            pass

    if thread:
        if thread.archived:
            await thread.edit(archived=False)
        message = await thread.send(embed=embed)
    else:
        first = min(members, key=lambda m: m["obsDt"])
        region = region_of(first)
        tag = discord.utils.get(channel.available_tags, name=region) if region else None
        created = await channel.create_thread(
            name=post_title(first), embed=embed, applied_tags=[tag] if tag else []
        )
        message = created.message
        db.execute(
            "INSERT OR REPLACE INTO posts VALUES (?,?,?)", (species, scope, created.thread.id)
        )
    db.execute(
        "INSERT OR REPLACE INTO groups VALUES (?,?,?,?)",
        (species, checklist_id, scope, message.id),
    )
    db.commit()
    if not thread and region:
        await notify_rba(channel, region, created.thread, first)


async def attach_checklist(session: aiohttp.ClientSession, o: dict, cache: dict) -> dict:
    """Add shared checklist id and comments from the checklist view."""
    sub_id = o["subId"]
    if sub_id not in cache:
        cache[sub_id] = await get_json(session, f"/product/checklist/view/{sub_id}")
        await asyncio.sleep(REQUEST_DELAY_SECONDS)
    cl = cache[sub_id]
    entry = next((e for e in cl.get("obs", []) if e.get("speciesCode") == o["speciesCode"]), {})
    return {
        **o,
        "checklistId": f"{o['locId']}|{o['obsDt']}",
        "subComments": cl.get("subComments") or "",
        "obsComments": entry.get("comments") or "",
    }


async def process_sighting(channel: discord.ForumChannel, o: dict):
    species, checklist_id = o["speciesCode"], o["checklistId"]
    scope = scope_of(o)
    previous = [
        json.loads(r[0])
        for r in db.execute(
            "SELECT data FROM sightings WHERE species_code=? AND checklist_id=?",
            (species, checklist_id),
        )
    ]
    try:
        await send_group(client, channel, species, checklist_id, scope, previous + [o])
    except discord.HTTPException:
        log.exception("Failed to post %s %s", species, checklist_id)
        return
    db.execute(
        "INSERT OR IGNORE INTO sightings VALUES (?,?,?,?,?)",
        (o["subId"], species, checklist_id, scope, json.dumps(o)),
    )
    db.commit()


async def update_existing_sightings(
    channel: discord.ForumChannel, observations: list[dict]
) -> set[tuple[str, str]]:
    current = {(o["subId"], o["speciesCode"]): o for o in observations}
    rows = db.execute(
        "SELECT sub_id, species_code, checklist_id, scope, data FROM sightings"
    ).fetchall()
    known = {(row[0], row[1]) for row in rows}
    groups: dict[tuple[str, str, str], list[dict]] = {}
    changed_groups = set()

    for row in rows:
        key = (row[0], row[1])
        latest = current.get(key)
        if not latest:
            continue
        saved = json.loads(row[4])
        merged = {**saved, **latest}
        scope = scope_of(merged)
        group = (row[1], row[2], scope)
        groups.setdefault(group, []).append(merged)
        if merged != saved or scope != row[3]:
            changed_groups.add(group)

    for group in changed_groups:
        species, checklist_id, scope = group
        members = groups[group]
        try:
            await send_group(client, channel, species, checklist_id, scope, members)
        except discord.HTTPException:
            log.exception("Failed to update %s %s", species, checklist_id)
            continue
        for member in members:
            db.execute(
                "UPDATE sightings SET scope=?, data=? WHERE sub_id=? AND species_code=?",
                (scope, json.dumps(member), member["subId"], species),
            )
        db.commit()
    return known


async def poll_once():
    channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    try:
        async with aiohttp.ClientSession() as session:
            obs = await get_json(
                session,
                f"/data/obs/{REGION}/recent/notable",
                detail="full",
                back=BACK_DAYS,
            )

            current = {(o["subId"], o["speciesCode"]) for o in obs}
            known = await update_existing_sightings(channel, obs)

            # checklistId is only known after the lookup, so order by subId; later
            # observers of a shared checklist edit the message already posted.
            todo = {}
            for o in sorted(obs, key=lambda o: sub_num(o["subId"])):
                k = (o["subId"], o["speciesCode"])
                if k not in known:
                    todo.setdefault(k, o)
            log.info("%d new sightings to process", len(todo))

            cache: dict = {}
            for i, (k, o) in enumerate(todo.items(), 1):
                log.info("Checklist %d/%d: %s (%s)", i, len(todo), k[0], o["comName"])
                try:
                    o = await attach_checklist(session, o, cache)
                except aiohttp.ClientError:
                    log.exception("Checklist lookup failed for %s; will retry", k)
                    continue
                await process_sighting(channel, o)
    except aiohttp.ClientError:
        log.exception("eBird request failed")
        return

    # Purge records that dropped off the API, then groups/posts with no sightings left.
    for sub_id, species in known - current:
        db.execute(
            "DELETE FROM sightings WHERE sub_id=? AND species_code=?", (sub_id, species)
        )
    db.execute(
        """DELETE FROM groups WHERE NOT EXISTS (
               SELECT 1 FROM sightings s
               WHERE s.species_code = groups.species_code
                 AND s.checklist_id = groups.checklist_id)"""
    )
    db.execute(
        """DELETE FROM posts WHERE NOT EXISTS (
               SELECT 1 FROM sightings s
               WHERE s.species_code = posts.species_code AND s.scope = posts.scope)"""
    )
    db.commit()


@tasks.loop(minutes=POLL_MINUTES)
async def poll():
    log.info("Polling cycle started")
    try:
        await poll_once()
    finally:
        log.info("Polling cycle completed")


REQUIRED_PERMS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    send_messages_in_threads=True,
    read_message_history=True,
    manage_channels=True,
    manage_roles=True,
    manage_threads=True,
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

        try:
            await ensure_region_tags(channel, REGIONS)
        except discord.HTTPException:
            log.exception("Could not create region tags; the bot needs Manage Channels")
        try:
            await ensure_region_forums(
                channel, REGION_GROUPS, DISCORD_CHANNEL_MOVE_DELAY_SECONDS
            )
        except discord.HTTPException:
            log.exception(
                "Could not sync regional channels; the bot needs Manage Channels and "
                "Manage Roles. Re-authorize it with: %s",
                invite,
            )

        if not poll.is_running():
            poll.start()


client = Bot(intents=discord.Intents.default())

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    client.run(DISCORD_TOKEN)
