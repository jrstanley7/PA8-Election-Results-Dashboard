# PA-8 Precinct Returns

An interactive precinct-level map of Pennsylvania's 8th Congressional District (Lackawanna, Wayne, Pike, and the PA-8 parts of Luzerne and Monroe counties), covering the 2022, 2024 and 2026 general elections.

**Open the map:** https://jrstanley7.github.io/PA8-Election-Results-Dashboard/ (or open `index.html` directly; it is one self-contained page and works offline).

> **2026 results are unofficial.** They come from the counties' election-night reports and will change slightly when the counties certify.

## What it shows

- **Results by precinct** for every partisan race on the ballot: President, U.S. Senate, Governor, row offices, U.S. House (PA-8), State Senate and State House.
- **Party registration** by precinct, and how each race ran ahead of or behind registration.
- **Change since 2022 and since 2024** for the U.S. House and Governor races, including raw vote changes.
- **Turnout**, and turnout change from 2022 to 2026.
- **Filters** by county, State Senate district and State House district; **precinct or municipality** view; **vote-size bubbles**; **side-by-side years**.
- **Search** for a precinct or town, a **sortable table** of every precinct, **CSV** copy/download, and **shareable links**: the current view is kept in the page address (for example `index.html#2026.cong.swing2022.Luzerne.muni`).

## Sources

| Data | Source |
|---|---|
| 2026 results, Lackawanna | Lackawanna County *Summary Results Report* by precinct (`G26.PCT12`), unofficial, 11/03/2026 10:02 PM — `sources/county/lackawanna/` |
| 2026 results, Wayne | Wayne County *Statement of Votes Cast by Precinct*, unofficial, 11/03/2026 10:30 PM — `sources/county/wayne/` |
| 2026 results, Pike | Pike County precinct detail workbook, unofficial, 11/03/2026 10:13 PM — `sources/county/pike/` |
| 2026 results, Luzerne | Luzerne County precinct detail workbook, unofficial, 11/03/2026 11:39 PM — `sources/county/luzerne/` |
| 2026 results, Monroe | Monroe County Election Results site, contest pages saved 11/04/2026 (agencies2.monroecountypa.gov/ElectionResults) — `sources/county/monroe/` |
| 2022 and 2024 results | PA Department of State precinct election returns (2022 General, 2024 General) |
| Party registration | PA Department of State precinct voter registration: 2026 General Primary rolls (used for 2026), 2024 General and 2022 General rolls |
| Precinct boundaries | U.S. Census Bureau 2020 TIGER/Line voting districts for the five counties |
| District line (for Ross Two) | U.S. Census Bureau 2022 congressional districts (118th Congress) |

The state and Census files are public and large, so they are downloaded by `scripts/fetch_sources.py` rather than stored in the repo.

## How the data is put together

- **Matching precincts to shapes.** Each county's 2026 precincts are matched by name to the 2020 Census voting districts. 2022 and 2024 results and all registration are joined by the state's precinct code. Every mapped 2026 precinct existed under the same code in 2024.
- **Only the PA-8 parts of split counties.** Luzerne's 27 PA-9 precincts and Monroe's PA-7 precincts (Eldred, Polk, Ross One) are left off. Butler Township Dist 05 (Luzerne) is split between PA-8 and PA-9; its U.S. House result is the PA-8 part only.
- **Precincts redrawn since 2020.**
  - Pike's Matamoras and Luzerne's Hazle Township Dist 01 each combine two 2020 voting districts.
  - Monroe has not published boundaries for precincts drawn since 2020. Middle Smithfield's four precincts are shown as two areas matching the 2020 West (One, Two) and East (Three, Four) districts; Tunkhannock's two are shown as the whole township.
  - Ross Two is Ross Township cut along the PA-8 line.
- **Parties.** Wayne, Pike and Luzerne reports do not label parties, so candidates are matched to parties by name and ballot order (Pennsylvania lists the governor's party first).
- **Turnout.** Monroe does not publish precinct ballot counts, so it is left out of 2026 ballots-cast turnout. 2022 and 2024 turnout use votes in the top race (Governor, President) because the state files have no ballot counts. *Turnout change since 2022* uses Governor votes divided by state registration in both years, so every county is included.
- **Checks.** While parsing, every county's precinct totals are checked against that county's own totals, and the 2022 and 2024 U.S. House totals match the certified results.

## Rebuilding the map

Needs Python 3.10+.

```bash
pip install -r requirements.txt
python scripts/fetch_sources.py   # download state + Census files into sources/
python scripts/build.py           # parse everything, write data/pa8.geojson
python scripts/render.py          # write index.html (template + data)
```

To change the page itself, edit `src/template.html` and rerun `scripts/render.py`. To update to certified 2026 results, replace the files in `sources/county/` and rerun `build.py` and `render.py`.

## Hosting on GitHub Pages

In the repository, open **Settings → Pages**, choose **Deploy from a branch**, pick `main` and `/ (root)`, and save. The map is then served at https://jrstanley7.github.io/PA8-Election-Results-Dashboard/.

## Layout

```
index.html               the map (generated)
data/pa8.geojson         precinct shapes + results + registration (generated)
src/template.html        the map page, with a placeholder for the data
scripts/fetch_sources.py downloads state and Census files
scripts/build.py         builds data/pa8.geojson
scripts/render.py        builds index.html
sources/county/          the 2026 county result files
```
