# Current region layout

`REGIONS` and `REGION_GROUPS` in `bot.py` currently match the map definitions in `georgia_map.py`. Region slugs are used for forum tags and channel names; `REGION_LABELS` supplies the map and report display names.

## Constraints

- Discord forums allow 20 tags, so there are at most 20 regions.
- All 159 counties must be assigned exactly once; `georgia_map.py` exits on a county mismatch.
- `REGION_GROUPS` must list every region exactly once.

## Regions and checklist workload

Checklist counts are summed from the 159-county Checklist Leaders board in `2026ytd_counts.html` (111,641 statewide). `county_info.html` combines that saved 2026 YTD snapshot with county population estimates and the current region assignments; it is not a live count.

| Geographic group | Region | Counties | 2025 population estimate | 2026 YTD checklists | Per 1,000 residents |
|---|---|---:|---:|---:|---:|
| Metro Atlanta | DeKalb County | 1 | 774,394 | 11,582 | 14.96 |
| Metro Atlanta | Fulton County | 1 | 1,098,791 | 10,126 | 9.22 |
| Metro Atlanta | Cobb County | 1 | 793,345 | 8,562 | 10.79 |
| Metro Atlanta | Gwinnett County | 1 | 1,018,099 | 5,201 | 5.11 |
| Metro Atlanta | Cherokee County | 1 | 299,273 | 2,504 | 8.37 |
| Coastal Georgia | Glynn County | 1 | 87,599 | 6,747 | 77.02 |
| West Georgia | Columbus-Fall Line | 6 | 269,119 | 1,929 | 7.17 |
| Northeast Georgia | Athens Area | 3 | 191,229 | 6,837 | 35.75 |
| East Georgia | Augusta Area | 2 | 375,748 | 1,841 | 4.90 |
| Central Georgia | Macon Area | 10 | 511,079 | 5,060 | 9.90 |
| Coastal Georgia | Chatham-Effingham Coast | 2 | 386,252 | 5,391 | 13.96 |
| Coastal Georgia | Mid-Coast Georgia | 4 | 194,507 | 4,539 | 23.34 |
| North Georgia | North Georgia Mountains | 20 | 966,385 | 13,385 | 13.85 |
| Northeast Georgia | Upper Piedmont Lakes | 10 | 865,116 | 5,354 | 6.19 |
| West Georgia | West Central Piedmont | 8 | 776,140 | 4,094 | 5.27 |
| Central Georgia | South Atlanta Piedmont | 15 | 1,277,426 | 6,806 | 5.33 |
| South Georgia | Southwest Georgia | 31 | 678,173 | 6,617 | 9.76 |
| Central Georgia | West Sandhills & Fall Line | 16 | 224,301 | 1,585 | 7.07 |
| East Georgia | East Sandhills | 22 | 452,072 | 2,828 | 6.26 |
| East Georgia | Upper Savannah | 4 | 63,700 | 653 | 10.25 |

The statewide denominator is 11,302,748 residents, or 9.88 checklists per 1,000 residents. Rates are weighted totals (region checklists divided by region population), not averages of county rates.

County membership is defined in `georgia_map.py`. Macon County is assigned to Macon Area, not West Sandhills & Fall Line.
`REGION_GROUPS` now represents broad geographic areas; checklist volume and per-capita rates do not determine group placement.

## Assessment against known data

- The five Metro Atlanta counties plus Glynn County produce 44,722 checklists, about 40.1% of the statewide total. DeKalb, Fulton, and Cobb are the top three counties in the saved leaderboard; Glynn also remains a major checklist center. These remain standalone regions, while their parent groups are now geographic.
- Restoring Columbus gives its six-county region 1,929 checklists. Muscogee contributes 1,367, about 70.9% of that region's total, supporting its role as the anchor.
- Geographic group totals (checklists / per 1,000 residents) are Metro Atlanta 37,975 / 9.53, North Georgia 13,385 / 13.85, Northeast Georgia 12,191 / 11.54, West Georgia 6,023 / 5.76, Central Georgia 13,451 / 6.68, East Georgia 5,322 / 5.97, South Georgia 6,617 / 9.76, and Coastal Georgia 16,677 / 24.95.
- Checklist volume remains uneven within and between the geographic groups: North Georgia Mountains has the largest region total at 13,385, while Upper Savannah has 653. The group labels describe geography, not workload tiers.
- Region-level rates range from 4.90 per 1,000 in Augusta Area to 77.02 in Glynn County. Athens Area (35.75) and Mid-Coast Georgia (23.34) are also above the statewide rate; these are regional activity differences, not group criteria.
- County-level 2025 population estimates and rates are joined in `county_info.html`; the population values come from the 2025 estimate column in the source county table. Rates can change with new checklist snapshots or population estimates.
- Macon Area has 10 counties, including Macon County. Its saved checklist total is 5,060.

The checklist values can be refreshed by replacing `2026ytd_counts.html` and regenerating `county_info.html`. Keep the matching county population table available when rebuilding the joined report.

## Colors

`COLORS` maps each region slug to its map color; `GROUP_COLORS` maps the eight geographic groups. Recheck neighboring color contrast if boundaries or colors change.

## Discord migration

The forum allows 20 tags. Remove the 16 obsolete tag names manually before restarting; four names are unchanged, and the bot will add the 16 new tags. The bot does not delete tags automatically.

At startup, the bot reuses and moves channels whose names exactly match a region slug. It creates a forum and banter channel for each new slug; the matching RBA thread is created when the first new sighting arrives. Channels with retired slugs are left in place and are not deleted or renamed automatically. For this migration, only the four identical slugs reuse their existing regional channel pairs; the other old pairs remain as historical channels while new pairs are created.

Changing a county's region affects future routing. Existing sighting posts and RBA threads are not automatically retagged or redistributed. Review and archive old regional channels manually after confirming the new channels and tags are working.

Regional startup provisioning, permission syncing, and ordering live in `utils/region_channels.py`. Keep `REGIONS` and `REGION_GROUPS` in `bot.py` and `georgia_map.py` synchronized. Run `python -m py_compile bot.py utils/region_channels.py utils/sync_category_permissions.py georgia_map.py` and `python georgia_map.py` before restarting the service.

The temporary `utils/sync_category_permissions.py` utility previews changes by default. It can apply category permissions to all categorized channels in the alert forum's guild except the forum ID configured by `DISCORD_CHANNEL_ID`; it is not limited to regional channels. Review the full preview before using `--apply`, because channel-specific overwrites on affected channels will be replaced by the category overwrites.