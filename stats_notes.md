# IPL Career Stats — Research Notes

Figures are IPL career aggregates (matches / runs / wickets) as of the **end of IPL 2025**.
Sources: ESPNcricinfo-derived figures, myKhel season tables, iplt20.com/ipl.com, cricfacts, sportsyaari, crex, advancecricket, cricketman2, cricbuzz-sourced articles. Where sources had merged IPL 2026 into career totals, the 2026 season row was subtracted.

## Null fields (1)

- **Yuzvendra Chahal** — `runs` is `null`. His 174 matches / 221 wickets through 2025 are confirmed by season tables, but no source isolates his IPL batting runs at the end-2025 cutoff (37 runs is his through-2026 total; his 2026 batting contribution could not be determined).

## Zero IPL appearances (4)

- **Jamie Smith** — never played an IPL match (unsold at the IPL 2026 auction).
- **Gus Atkinson** — never played an IPL match (signed by KKR for 2024 but withdrew before playing; unsold in 2025 and 2026 auctions).
- **Bevon Jacobs** — did not play a single IPL 2025 game.
- **Allah Ghazanfar** — KKR 2024 replacement, MI 2025 signing; ruled out before the 2025 season with a spine fracture (IPL debut came in 2026).

## Corrected premises (2)

- **Tom Banton** — originally assumed to have zero IPL games; he actually played 2 matches for KKR in 2020 (18 runs). Recorded as 2/18/0.
- **Litton Das** — originally assumed zero; he played 1 match for KKR in 2023 (4 runs). Recorded as 1/4/0.

## Uncertain / low-confidence figures

- **Shimron Hetmyer** — 1482 runs (majority) vs 1483 in one source; one-run difference in the 2023 season tally.
- **Glenn Maxwell** — 141 / 2819 / 41 (majority, ipl.com + ESPNcricinfo-sourced article) vs 2813 runs / 40 wickets in one source.
- **Mitchell Marsh** — 55 / 1292 / 37 derived from consistent arithmetic across pre/post-2026 snapshots; reasonably confident.
- **Manish Pandey** — 174 matches (majority) vs 175 in one ESPNcricinfo-cited article; runs 3942 confirmed.
- **Mayank Agarwal** — 131 / 2756 verified via season splits (123 through 2023 + 4 + 4); one source says 130 matches.
- **Mark Wood** — runs 12 is the least directly verified figure (myKhel profile page is stale); corroborated by cricfacts, advancecricket and sportsyaari.
- **T Natarajan** — runs 3 comes from his 2020 season only; several season cells show dashes. Low confidence, consistent across sources.
- **Trent Boult** — 143 wickets assembled from a season table (121 through 2024) + 22 in 2025; consistent with a through-2026 total of 145.
- **Mohit Sharma** — runs 125 (majority: Insidesport, AdvanceCricket, CricIns) vs 127 (myKhel); 120 matches / 134 wickets are ESPNcricinfo-confirmed.
- **Karn Sharma** — runs 352 (majority: ipl.com, Cricfacts, KhelNow, Sportstak, CricXtasy) vs 351 (myKhel season table); 90 matches / 83 wickets unanimous.
- **Adil Rashid** — runs 22 (myKhel, SportsYaari, Insidesport) vs 21 (AdvanceCricket); 3 matches / 2 wickets agreed.
- **Tabraiz Shamsi** — runs 2 from a single source (cricketstatus.com: 5 matches, 1 innings, 2 runs); matches (5) and wickets (3) multi-source confirmed.
- **Angkrish Raghuvanshi** — 22 matches (majority) vs 23 in one source; runs 463 solid (163 in 2024 + 300 in 2025).
- **Spencer Johnson** — 9 / 8 / 5 is the end-2025 figure; through-2026 sources show 12 / 7 (excluded per cutoff).
- **Rahul Chahar** — 79 / 129 / 75 end-2025 (one 2026 match with 0 wickets excluded); the 129-run figure is the 2026-inclusive ipl.com number and he is unlikely to have batted in that single 2026 match — minor risk.
- **Abdul Samad** — season match-counts conflict across sources (2023: 9 vs 11/13; 2025: 13 vs 14); used 9 and 13 from detailed season pages, consistent with crex's 71-match/857-run career total; runs 741 (one outlier source says 726); wickets 2 unanimous.
- **Yash Thakur** — used 21 matches / 25 wickets (myKhel, cricbuzz, cricketman2); one source claims 3 matches/3 wickets in 2025.
- **Vaibhav Arora** — used 32 matches / 36 wickets (confirmed by myKhel's "36 wickets from 32 IPL matches" statement); one source says 9 matches/8 wickets in 2023 vs 5/5 everywhere else.
- **Kwena Maphaka** — 4 / 8 / 2; the 8 runs come from a single cricbuzz live scorecard (8*(2) vs PBKS 2025), tail-end batting — slight risk.
- **Musheer Khan** — 1 / 0 / 1; his only IPL match was as a 2025 Qualifier 1 impact substitute (0 off 3, 1/27).
- **David Miller** — 141 / 3077 derived from season-row sums, but cross-checked three independent ways (ipl.com through-2026 minus a published 2026 row; KXIP-era subtotal vs an independent article; 2024/2025 seasons confirmed by 4–6 sources each).
- **Aiden Markram** — 57 / 1440 / 6; IPL debut confirmed as 2021 for PBKS (one source wrongly claims 2018); 2023 = 13 matches (5 sources) vs 14 (one source).

## Method notes

- All figures are IPL-only, never international or overall T20.
- Pure batters/wicket-keepers with no IPL wickets have `"wkts": 0`; bowlers keep their actual IPL runs.
- Youngsters with confirmed zero IPL appearances have all zeros; no numbers were invented — unfindable fields would be `null` (only Chahal's runs).
- No player required a full-null entry; every player has at least a verified match count.
