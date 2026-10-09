import re

import discord

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Bounding box for Georgia, USA
GA_LAT_MIN, GA_LAT_MAX = 30.3556, 35.0007
GA_LON_MIN, GA_LON_MAX = -85.6052, -80.8397

# Regex for decimal-degree formats like "34.05498° N, 84.67575° W",
# plus the existing DD, DDM, and DMS coordinate styles.
COORD_PATTERN = re.compile(
    r'(?P<lat_deg>-?\d+(?:\.\d+)?)(?:[°\s]*(?P<lat_min>\d+(?:\.\d+)?))?(?:[\'\s]*(?P<lat_sec>\d+(?:\.\d+)?))?[\"\s]*(?P<lat_dir>[NSns])?'
    r'[\s,;\/]+'
    r'(?P<lon_deg>-?\d+(?:\.\d+)?)(?:[°\s]*(?P<lon_min>\d+(?:\.\d+)?))?(?:[\'\s]*(?P<lon_sec>\d+(?:\.\d+)?))?[\"\s]*(?P<lon_dir>[EWew])?'
)
DECIMAL_DIRECTION_PATTERN = re.compile(
    r'(?P<lat_value>-?\d+(?:\.\d+)?)\s*(?:°\s*)?(?P<lat_dir>[NSns])?'
    r'[\s,;\/]+'
    r'(?P<lon_value>-?\d+(?:\.\d+)?)\s*(?:°\s*)?(?P<lon_dir>[EWew])?'
)


def convert_to_decimal(deg, mins, secs, direction):
    """Converts degrees, minutes, seconds, and direction to standard decimal degrees."""
    decimal = float(deg)
    if mins:
        decimal += float(mins) / 60.0
    if secs:
        decimal += float(secs) / 3600.0

    if decimal < 0:
        return decimal

    if direction and direction.upper() in ["S", "W"]:
        decimal = -decimal

    return decimal


def find_georgia_coordinates(text: str) -> list[dict[str, str]]:
    if not text:
        return []

    found_coords: list[dict[str, str]] = []
    seen: set[str] = set()
    patterns = [COORD_PATTERN, DECIMAL_DIRECTION_PATTERN]

    for pattern in patterns:
        for match in pattern.finditer(text):
            if len(found_coords) >= 4:
                break

            gd = match.groupdict()
            lat_raw = gd.get("lat_value") or gd.get("lat_deg")
            lon_raw = gd.get("lon_value") or gd.get("lon_deg")
            if lat_raw is None or lon_raw is None:
                continue

            try:
                lat = convert_to_decimal(lat_raw, gd.get("lat_min"), gd.get("lat_sec"), gd.get("lat_dir"))
                lon = convert_to_decimal(lon_raw, gd.get("lon_min"), gd.get("lon_sec"), gd.get("lon_dir"))
            except (TypeError, ValueError):
                continue

            if (GA_LAT_MIN <= lat <= GA_LAT_MAX) and (GA_LON_MIN <= lon <= GA_LON_MAX):
                lat_str = f"{lat:.5f}"
                lon_str = f"{lon:.5f}"
                key = f"{lat_str},{lon_str}"
                if key in seen:
                    continue
                seen.add(key)
                found_coords.append(
                    {
                        "original": match.group(0).strip(),
                        "decimal": f"{lat_str}, {lon_str}",
                        "google_url": f"https://maps.google.com/?q={lat_str},{lon_str}",
                        "apple_url": f"https://maps.apple.com/?q={lat_str},{lon_str}",
                    }
                )

    return found_coords


def build_georgia_coordinates_embed(message: discord.Message, found_coords: list[dict[str, str]]) -> discord.Embed:
    embed = discord.Embed(
        title="📍 Georgia Coordinates Detected",
        # description=f"Found {len(found_coords)} valid location match{'es' if len(found_coords) > 1 else ''} inside Georgia.",
        color=discord.Color.teal(),
    )

    for idx, coord in enumerate(found_coords, start=1):
        embed.add_field(
            name=f"Match #{idx}",
            value=f"**Original:** `{coord['original']}`\n"
            # f"**Decimals:** `{coord['decimal']}`\n"
            f"[🌐 Google Maps]({coord['google_url']}) | [🍏 Apple Maps]({coord['apple_url']})",
            inline=False,
        )

    return embed


@client.event
async def on_message(message):
    if message.author.bot:
        return

    found_coords = find_georgia_coordinates(message.content)
    if found_coords:
        await message.channel.send(embed=build_georgia_coordinates_embed(message, found_coords))


if __name__ == "__main__":
    client.run("YOUR_BOT_TOKEN")