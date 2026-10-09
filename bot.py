import asyncio
import json
import logging
import os
import sqlite3

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from georgia_map import REGION_GROUPS, REGIONS
from gps import build_georgia_coordinates_embed, find_georgia_coordinates

load_dotenv()

EBIRD_KEY = os.environ["EBIRD_API_KEY"]
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
REGION = os.environ.get("EBIRD_REGION", "US-GA")
BACK_DAYS = int(os.environ.get("EBIRD_BACK_DAYS", "14"))
POLL_MINUTES = int(os.environ.get("POLL_MINUTES", "15"))
DB_PATH = os.environ.get("DB_PATH", "sightings.db")
REQUEST_DELAY_SECONDS = float(os.environ.get("REQUEST_DELAY_SECONDS", "3"))
PRUNE_OLD_SIGHTINGS = os.environ.get("PRUNE_OLD_SIGHTINGS", "true").strip().lower() not in {"0", "false", "no", "off"}
VERBOSE_LOGGING = os.environ.get("VERBOSE_LOGGING", "false").strip().lower() not in {"0", "false", "no", "off"}
MAX_RETRIES = 5
SCHEMA_VERSION = 2
WELCOME_CHANNEL = "rules-and-info"
WELCOME_MESSAGE = (
    "# Welcome to the Georgia Birding Discord!\n\nWe are glad you are here! To keep this server "
    "a helpful and easy-to-use resource for all Georgia birders, all members are required to "
    "follow the rules below. Posts that do not adhere to these rules may be removed at an admin's "
    "discretion. Repeated violations may result in temporary suspension or removal from the "
    "server.\n\n"
    "* :one: **Be respectful!** The Georgia birding community is large and diverse, so please "
    "consider the language you are using so as to not be offensive.\n"
    "* :two: **Stay On Topic:** Before making a post, always double check that you've selected "
    "the appropriate channel.\n"
    "* :three: **Posts related to advertising, marketing, solicitation, membership drives, or "
    "petitions are not acceptable**. Limited exceptions may be made by moderators for relevant "
    "birding events, conservation initiatives, or announcements from Birds Georgia and trusted "
    "partners within the Georgia birding community.\n"
    "* :four: **We expect all members to model the [American Birding Association's Code of Ethics]"
    "(<https://www.aba.org/aba-code-of-birding-ethics/>):**\n"
    "  - Respect and promote birds and their environment\n"
    "  - Respect and promote the birding community and its individual members\n"
    "  - Respect and promote the law and the rights of others\n"
    "* :five: **We require users to share your full name (first and last) as your display name "
    "(aka nickname)**. Integrity, safety and transparency are an important part of birding and "
    "using a false or misleading identity is contrary to that requirement.\n\n"
    "# :point_right: Ready to join?\n"
    "*Click the Agree button below and submit your full name (no abbreviations, initials, or pseudonyms).*"
)
NICKNAME_BUTTON_ID = "thrasher:set_nickname"

API = "https://api.ebird.org/v2"
HEADERS = {"x-ebirdapitoken": EBIRD_KEY}

log = logging.getLogger("thrasherbot")

# Region slug -> eBird county names. Slugs are also forum tags and channel prefixes.
# Keep this configuration synchronized with georgia_map.py.
COUNTY_REGION = {c.lower(): r for r, counties in REGIONS.items() for c in counties}
REGION_TO_CATEGORY = {
    region: category
    for category, regions in REGION_GROUPS.items()
    for region in regions
}

MODERATOR_CHANNEL_NAME = os.environ.get("MODERATOR_CHANNEL_NAME", "moderator-only")
RARE_CHECKLIST_ALERT_THRESHOLD = int(os.environ.get("RARE_CHECKLIST_ALERT_THRESHOLD", "4"))
RARE_BIRDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rare_birds.txt")


def normalize_species(name: str) -> str:
    return " ".join(name.replace("’", "'").lower().split())


def load_rare_birds() -> set[str]:
    try:
        with open(RARE_BIRDS_PATH, encoding="utf-8") as f:
            return {normalize_species(line) for line in f if line.strip()}
    except FileNotFoundError:
        return set()


RARE_BIRDS = load_rare_birds()


def county_slug(county: str) -> str:
    return county.lower().removesuffix(" county").replace(" ", "-")


def channel_slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def region_chat_channel_name(region: str) -> str:
    return f"{region}-chat"


def rba_forum_name(category: str, regions: list[str]) -> str:
    if len(regions) == 1:
        return f"{channel_slug(regions[0])}-rba"
    return f"{channel_slug(category)}-rba"


def region_alert_thread_name(region: str) -> str:
    return f"eBird RBA - {region.replace('-', ' ').title()}"


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
    -- One persistent alert thread per region's RBA forum.
    CREATE TABLE IF NOT EXISTS region_alert_threads (
        region TEXT PRIMARY KEY,
        thread_id INTEGER NOT NULL,
        message_id INTEGER
    );
    -- One message per species per (shared) checklist.
    CREATE TABLE IF NOT EXISTS groups (
        species_code TEXT NOT NULL,
        checklist_id TEXT NOT NULL,
        scope TEXT NOT NULL,
        message_id INTEGER NOT NULL,
        PRIMARY KEY (species_code, checklist_id)
    );
    -- Rare checklists that need moderator release before posting to the main RBA forum.
    CREATE TABLE IF NOT EXISTS review_queue (
        checklist_id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    return o.get("locationPrivate") is False and bool(o.get("locId"))


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

    loc_name = o.get("locName", "Unknown location")
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
            f"[{loc_name}](https://ebird.org/hotspot/{o['locId']})"
            if is_hotspot(o) and o.get("locId")
            else loc_name
        ),
        inline=False,
    )
    if o.get("subnational2Name"):
        embed.add_field(name="County", value=o["subnational2Name"])
    embed.add_field(
        name="Map",
        value=(
            f"[Google Maps](https://maps.google.com/?q={o['lat']},{o['lng']}) | "
            f"[Apple Maps](https://maps.apple.com/?ll={o['lat']},{o['lng']})"
        ),
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


def format_flagged_checklist_embed(checklist_id: str, members: list[dict]) -> discord.Embed:
    ordered = sorted(members, key=lambda m: sub_num(m["subId"]))
    first = ordered[0]
    species_names = sorted({m["comName"] for m in ordered if normalize_species(m["comName"]) in RARE_BIRDS})
    species_text = "\n".join(f"• {name}" for name in species_names[:10])
    if len(species_names) > 10:
        species_text += f"\n… and {len(species_names) - 10} more"

    embed = discord.Embed(
        title="Rare checklist flagged for review",
        description=(
            f"This checklist has {len(ordered)} rare bird sighting(s) and must be released before it can be posted to the main RBA channel."
            f"\n[View checklist](https://ebird.org/checklist/{first['subId']})"
        ),
        color=discord.Color.orange(),
    )
    if first.get("subnational2Name"):
        embed.add_field(name="County", value=first["subnational2Name"])
    embed.add_field(name="Date", value=first["obsDt"])
    embed.add_field(name="Rare species", value=species_text or "Unknown", inline=False)
    embed.add_field(name="Checklist ID", value=checklist_id, inline=False)
    return embed


class ChecklistReviewView(discord.ui.View):
    def __init__(self, checklist_id: str):
        super().__init__(timeout=None)
        self.checklist_id = checklist_id

    @discord.ui.button(
        label="Release to main RBA",
        style=discord.ButtonStyle.success,
        custom_id="thrasher:release_checklist",
    )
    async def release_checklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Only moderators can release a flagged checklist.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await release_flagged_checklist(self.checklist_id)
            if interaction.message is not None:
                await interaction.message.edit(content=f"Checklist {self.checklist_id} released to the main RBA channel.", view=None)
            await interaction.followup.send(
                f"Checklist {self.checklist_id} has been resent to the main RBA channel.",
                ephemeral=True,
            )
        except Exception:
            log.exception("Failed to release flagged checklist %s", self.checklist_id)
            await interaction.followup.send(
                "The checklist could not be released right now. Please try again later.",
                ephemeral=True,
            )


async def get_thread(client: discord.Client, thread_id: int):
    try:
        ch = client.get_channel(thread_id) or await client.fetch_channel(thread_id)
        return ch if isinstance(ch, discord.Thread) else None
    except discord.NotFound:
        return None


def unwrap_thread(result):
    return getattr(result, "thread", result)


def scope_of(o: dict) -> str:
    if is_hotspot(o) and o.get("locId"):
        return o["locId"]
    return "county:" + o.get("subnational2Code", o.get("subnational2Name", "unknown"))


async def notify_region_chat(client: discord.Client, channel: discord.ForumChannel, region: str, post: discord.Thread, o: dict):
    """Create or update a per-region alert post in the category RBA forum."""
    category = REGION_TO_CATEGORY.get(region)
    if category:
        forum_name = rba_forum_name(category, REGION_GROUPS.get(category, []))
        target_forum = discord.utils.get(channel.guild.channels, name=forum_name)
        if isinstance(target_forum, discord.ForumChannel):
            thread_name = region_alert_thread_name(region)
            row = db.execute(
                "SELECT thread_id, message_id FROM region_alert_threads WHERE region=?",
                (region,),
            ).fetchone()
            thread = await get_thread(client, row[0]) if row else None
            if thread is None:
                try:
                    async for existing in target_forum.archived_threads(limit=100):
                        if existing.name == thread_name:
                            thread = existing
                            break
                except discord.HTTPException:
                    thread = None
                if thread is None:
                    try:
                        created = await target_forum.create_thread(
                            name=thread_name,
                            content=f"eBird alerts for {region.replace('-', ' ').title()}"
                        )
                        thread = unwrap_thread(created)
                    except discord.HTTPException:
                        log.exception("Failed to create alert thread for %s in %s", region, forum_name)
                        thread = None
            if thread is not None:
                location_name = o.get("locName", "Unknown location")
                message_text = (
                    f"[{o.get('subnational2Name', 'Unknown')}] [{o['comName']}]({post.jump_url}) - "
                    f"{location_name} ({o['obsDt'][:10]})"
                )
                message_id = row[1] if row else None
                updated = False
                if message_id is not None:
                    try:
                        message = await thread.fetch_message(message_id)
                        lines = [line.strip() for line in (message.content or "").splitlines() if line.strip()]
                        if message_text not in lines:
                            await message.edit(content="\n".join(lines + [message_text]))
                            updated = True
                        db.execute(
                            "INSERT OR REPLACE INTO region_alert_threads VALUES (?, ?, ?)",
                            (region, thread.id, message.id),
                        )
                        db.commit()
                    except (discord.NotFound, discord.HTTPException):
                        message_id = None
                if not updated and message_id is None:
                    try:
                        message = await thread.send(message_text)
                        db.execute(
                            "INSERT OR REPLACE INTO region_alert_threads VALUES (?, ?, ?)",
                            (region, thread.id, message.id),
                        )
                        db.commit()
                    except discord.HTTPException:
                        log.exception("Failed to post alert to %s", thread_name)


def post_title(o: dict) -> str:
    county = o.get("subnational2Name", "Unknown")
    title = f"[{county}] {o['comName']} ({o['obsDt'][:10]})"
    if is_hotspot(o) and o.get("locName"):
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
            log.info("Reopening thread %s for %s %s", thread.id, species, checklist_id)
            await thread.edit(archived=False)
        log.info("Sending update to existing thread %s for %s %s", thread.id, species, checklist_id)
        message = await thread.send(embed=embed)
    else:
        first = min(members, key=lambda m: m["obsDt"])
        region = region_of(first)
        category = REGION_TO_CATEGORY.get(region) if region else None
        tag = discord.utils.get(channel.available_tags, name=category) if category else None
        log.info("Creating new thread for %s %s in %s with tag %s (region=%s, category=%s)", species, checklist_id, channel.name, getattr(tag, "name", None), region, category)
        created = await channel.create_thread(
            name=post_title(first), embed=embed, applied_tags=[tag] if tag else []
        )
        thread_obj = unwrap_thread(created)
        message = created.message if hasattr(created, "message") else None
        if message is None:
            message = await thread_obj.send(embed=embed)
        db.execute(
            "INSERT OR REPLACE INTO posts VALUES (?,?,?)", (species, scope, thread_obj.id)
        )
    db.execute(
        "INSERT OR REPLACE INTO groups VALUES (?,?,?,?)",
        (species, checklist_id, scope, message.id),
    )
    db.commit()
    log.info("Stored group %s %s in thread %s with message %s", species, checklist_id, getattr(created.thread if not thread else thread, "id", "?"), message.id)
    if not thread and region:
        await notify_region_chat(client, channel, region, created.thread, first)


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


async def flag_checklist(channel: discord.ForumChannel, checklist_id: str, members: list[dict]):
    if db.execute(
        "SELECT 1 FROM review_queue WHERE checklist_id=?",
        (checklist_id,),
    ).fetchone():
        return

    moderator_channel = discord.utils.get(channel.guild.text_channels, name=MODERATOR_CHANNEL_NAME)
    if moderator_channel is None:
        log.warning("Moderator channel #%s was not found; checklist %s will remain unposted.", MODERATOR_CHANNEL_NAME, checklist_id)
        return

    embed = format_flagged_checklist_embed(checklist_id, members)
    view = ChecklistReviewView(checklist_id)
    try:
        message = await moderator_channel.send(embed=embed, view=view)
    except discord.HTTPException:
        log.exception("Failed to post moderator review for checklist %s to #%s", checklist_id, MODERATOR_CHANNEL_NAME)
        return

    self.add_view(view, message_id=message.id)
    db.execute(
        "INSERT INTO review_queue (checklist_id, data, channel_id, message_id) VALUES (?,?,?,?)",
        (checklist_id, json.dumps(members), moderator_channel.id, message.id),
    )
    db.commit()
    log.info("Flagged checklist %s for moderator review; %s rare sightings", checklist_id, len(members))


async def release_flagged_checklist(checklist_id: str):
    row = db.execute(
        "SELECT data FROM review_queue WHERE checklist_id=?",
        (checklist_id,),
    ).fetchone()
    if row is None:
        return

    main_channel = client.get_channel(CHANNEL_ID) or await client.fetch_channel(CHANNEL_ID)
    if not isinstance(main_channel, discord.ForumChannel):
        raise TypeError(f"Channel {CHANNEL_ID} is not a forum channel")

    members = json.loads(row[0])
    for o in sorted(members, key=lambda m: (m["speciesCode"], sub_num(m["subId"]))):
        await process_sighting(main_channel, o)

    db.execute("DELETE FROM review_queue WHERE checklist_id=?", (checklist_id,))
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
                if VERBOSE_LOGGING:
                    log.info("Checklist %d/%d: %s (%s)", i, len(todo), k[0], o["comName"])
                try:
                    o = await attach_checklist(session, o, cache)
                except aiohttp.ClientError:
                    log.exception("Checklist lookup failed for %s; will retry", k)
                    continue

                checklist_id = o["checklistId"]
                rare_members = [o] if normalize_species(o["comName"]) in RARE_BIRDS else []
                if len(rare_members) > RARE_CHECKLIST_ALERT_THRESHOLD:
                    await flag_checklist(channel, checklist_id, rare_members)
                    continue
                await process_sighting(channel, o)
    except aiohttp.ClientError:
        log.exception("eBird request failed")
        return

    if PRUNE_OLD_SIGHTINGS:
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
    else:
        log.info("Pruning disabled by PRUNE_OLD_SIGHTINGS; keeping historical sightings in SQLite.")


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
    manage_threads=True,
)


@app_commands.command(name="nickname", description="Set your server nickname and receive the member role.")
@app_commands.guild_only()
async def nickname_command(interaction: discord.Interaction, nickname: app_commands.Range[str, 1, 32]):
    await set_member_nickname(interaction, nickname)


async def set_member_nickname(interaction: discord.Interaction, nickname: str):
    guild = interaction.guild
    member = interaction.user
    if guild is None or not isinstance(member, discord.Member):
        await interaction.response.send_message("This command is only available in a server.", ephemeral=True)
        return

    nickname = nickname.strip()
    if not nickname:
        log.warning("Nickname command rejected empty value for user %s in guild %s", member.id, guild.id)
        await interaction.response.send_message("Enter your full name to set your nickname.", ephemeral=True)
        return
    parts = nickname.split()
    if len(parts) < 2:
        log.warning("Nickname command rejected malformed value for user %s in guild %s: %r", member.id, guild.id, nickname)
        await interaction.response.send_message("Please enter your full name with at least one space in between.", ephemeral=True)
        return

    role = next((role for role in guild.roles if role.name.casefold() == "member"), None)
    bot_member = guild.me
    if role is None:
        log.warning("Nickname command failed: member role not found in guild %s", guild.id)
        await interaction.response.send_message("The server's member role was not found.", ephemeral=True)
        return
    if bot_member is None or not bot_member.guild_permissions.manage_roles or not bot_member.guild_permissions.manage_nicknames:
        log.warning(
            "Nickname command failed: bot lacks required guild permissions in guild %s; manage_roles=%s manage_nicknames=%s",
            guild.id,
            bool(bot_member and bot_member.guild_permissions.manage_roles),
            bool(bot_member and bot_member.guild_permissions.manage_nicknames),
        )
        await interaction.response.send_message(
            "The bot needs Manage Roles and Manage Nicknames permissions to use this command.",
            ephemeral=True,
        )
        return
    if role >= bot_member.top_role or member.top_role >= bot_member.top_role:
        log.warning(
            "Nickname command failed because hierarchy check failed in guild %s: member_top=%s bot_top=%s target_top=%s",
            guild.id,
            role.position,
            bot_member.top_role.position if bot_member else None,
            member.top_role.position,
        )
        await interaction.response.send_message(
            "The bot's highest role must be above both your highest role and the member role.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    role_added = role in member.roles
    try:
        if not role_added:
            await member.add_roles(role, reason="User set their server nickname")
            role_added = True
        await member.edit(nick=nickname, reason="User changed their server nickname")
    except discord.Forbidden as error:
        log.warning(
            "Discord denied nickname update for member %s in guild %s: %s",
            member.id, guild.id, error,
        )
        if role_added and member.id == guild.owner_id:
            message = (
                "The member role is in place, but Discord does not allow the bot to change the "
                "server owner's nickname. Please update it yourself in the server."
            )
        elif role_added:
            message = (
                "The member role is in place, but Discord rejected the nickname change. "
                "Ask an admin to verify the bot has Manage Nicknames and its highest role "
                "is above yours."
            )
        else:
            message = "The bot could not assign the member role. Check its role permissions and hierarchy."
        await interaction.followup.send(message, ephemeral=True)
        return
    except discord.HTTPException:
        message = (
            "The member role was assigned, but Discord could not update your nickname."
            if role_added
            else "Discord could not assign the member role. Please try again later."
        )
        await interaction.followup.send(message, ephemeral=True)
        return

    await interaction.followup.send("Nickname updated and member role assigned.", ephemeral=True)


class NicknameModal(discord.ui.Modal, title="Set your server nickname"):
    full_name = discord.ui.TextInput(
        label="Full name",
        placeholder="Enter your first and last name",
        max_length=32,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await set_member_nickname(interaction, self.full_name.value)


class NicknameView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="I agree",
        style=discord.ButtonStyle.primary,
        custom_id=NICKNAME_BUTTON_ID,
    )
    async def set_nickname(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NicknameModal())


class Bot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(nickname_command)
        self.commands_synced = False
        self.add_view(NicknameView())
        self.welcome_panel_ready = False

    async def restore_review_queue(self):
        rows = db.execute(
            "SELECT checklist_id, channel_id, message_id FROM review_queue"
        ).fetchall()
        for checklist_id, channel_id, message_id in rows:
            try:
                channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            except (discord.Forbidden, discord.NotFound):
                log.warning("Could not access review channel %s for checklist %s", channel_id, checklist_id)
                continue

            if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
                continue

            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                log.warning(
                    "Review message %s for checklist %s was deleted; removing stale queue entry",
                    message_id,
                    checklist_id,
                )
                db.execute("DELETE FROM review_queue WHERE checklist_id=?", (checklist_id,))
                db.commit()
                continue

            view = ChecklistReviewView(checklist_id)
            self.add_view(view, message_id=message.id)
            try:
                await message.edit(view=view)
            except discord.HTTPException:
                log.exception("Could not reattach review button to checklist %s message %s", checklist_id, message.id)
                continue
            log.info("Reattached review queue message for checklist %s", checklist_id)

    async def ensure_welcome_panel(self, guild: discord.Guild):
        channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL)
        if channel is None:
            log.warning("Welcome channel #%s was not found", WELCOME_CHANNEL)
            return False

        existing = None
        try:
            async for message in channel.history(limit=100):
                if message.author == self.user:
                    existing = message
                    break
        except discord.Forbidden:
            log.warning("Cannot read recent messages in #%s to find the welcome panel", WELCOME_CHANNEL)
        except discord.HTTPException:
            log.exception("Could not check #%s for the welcome panel", WELCOME_CHANNEL)

        if existing is not None:
            try:
                await existing.edit(
                    content=WELCOME_MESSAGE,
                    view=NicknameView(),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                log.info("Refreshed nickname welcome panel in #%s", WELCOME_CHANNEL)
                return True
            except discord.HTTPException:
                log.exception("Could not refresh the nickname welcome panel in #%s", WELCOME_CHANNEL)
                return False

        try:
            await channel.send(
                WELCOME_MESSAGE,
                view=NicknameView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            log.info("Posted nickname welcome panel in #%s", WELCOME_CHANNEL)
            return True
        except discord.HTTPException:
            log.exception("Could not post the nickname welcome panel in #%s", WELCOME_CHANNEL)
            return False

    async def on_message(self, message):
        if message.author.bot:
            return

        found_coords = find_georgia_coordinates(message.content)
        if not found_coords:
            return

        await message.channel.send(embed=build_georgia_coordinates_embed(message, found_coords))

    async def on_ready(self):
        if not self.commands_synced:
            try:
                await self.tree.sync()
                self.commands_synced = True
                log.info("Application commands synced")
            except discord.HTTPException:
                log.exception("Could not sync application commands")

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

        if not self.welcome_panel_ready:
            self.welcome_panel_ready = await self.ensure_welcome_panel(channel.guild)

        await self.restore_review_queue()

        if not poll.is_running():
            poll.start()


intents = discord.Intents.default()
intents.message_content = True
client = Bot(intents=intents)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if VERBOSE_LOGGING else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    client.run(DISCORD_TOKEN)
