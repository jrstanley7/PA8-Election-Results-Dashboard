"""Download the public state and Census files the build needs (they are too large to keep in the repo).

Usage: python scripts/fetch_sources.py
Files land in sources/state/ and sources/census/ (both git-ignored). Already-downloaded files are skipped.
"""
import io
import os
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOS = "https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/bulk-data"
TIGER = "https://www2.census.gov/geo/tiger"

# PA Department of State precinct files: (saved as, URL)
STATE = [
    ("vr2026p.txt", f"{DOS}/2026-general-primary/vr/voterregistration_2026_primary.txt"),
    ("vr2024g.txt", f"{DOS}/2024-general-election/vr/vrstat2024_g(9187)_20241223.txt"),
    ("er2024g.txt", f"{DOS}/2024-general-election/er/erstat_2024_g_268768_20250129.txt"),
    ("er2022g.txt", f"{DOS}/ElectionReturns_2022_General_PrecinctReturns.txt"),
    ("vr2022g.txt", f"{DOS}/VoterRegistration_2022_General_Precinct.txt"),
]
# Census 2020 voting districts for the five PA-8 counties, and the 2022 congressional districts
CENSUS = [f"{TIGER}/TIGER2020PL/LAYER/VTD/2020/tl_2020_42{fips}_vtd20.zip" for fips in ("069", "079", "089", "103", "127")]
CENSUS.append(f"{TIGER}/TIGER2022/CD/tl_2022_42_cd118.zip")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (pa8-precinct-map build)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main():
    state_dir = os.path.join(ROOT, "sources", "state")
    census_dir = os.path.join(ROOT, "sources", "census")
    os.makedirs(state_dir, exist_ok=True)
    os.makedirs(census_dir, exist_ok=True)
    for name, url in STATE:
        dest = os.path.join(state_dir, name)
        if os.path.exists(dest):
            print("have", name)
            continue
        print("fetching", name)
        open(dest, "wb").write(get(url))
    for url in CENSUS:
        base = os.path.basename(url)[:-4]
        if os.path.exists(os.path.join(census_dir, base + ".shp")):
            print("have", base)
            continue
        print("fetching", base)
        with zipfile.ZipFile(io.BytesIO(get(url))) as z:
            for member in z.namelist():
                if member.endswith((".shp", ".shx", ".dbf", ".prj", ".cpg")):
                    z.extract(member, census_dir)


if __name__ == "__main__":
    main()
