"""Combine county precinct results, state precinct returns and registration, and 2020 Census voting-district
shapes into one GeoJSON for the map.

Usage: python scripts/build.py            (writes data/pa8.geojson)
Run scripts/fetch_sources.py first to download the state and Census files.
Feature properties: name, county, muni, reg, ballots, mail, pr (party registration), sd/hd (legislative districts),
y: {year: {contest: {candidate: votes}}}. Candidate labels are canonical ("DEM SHAPIRO / DAVIS") so totals sum
across counties. Every county total is checked against the county's own report while parsing.
"""
import json, re, sys, os
import shapefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTY_DIR = os.path.join(ROOT, "sources", "county")
STATE_DIR = os.path.join(ROOT, "sources", "state")
CENSUS_DIR = os.path.join(ROOT, "sources", "census")
CACHE_DIR = os.path.join(ROOT, "build")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "pa8.geojson")
num = lambda s: int(s.replace(",", ""))


def pdf_text(path):
    """Text of every page, pages joined by a marker line; cached in build/ because large PDFs are slow to read."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = os.path.join(CACHE_DIR, os.path.basename(path) + ".txt")
    if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(path):
        return open(cache, encoding="utf8").read()
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = "\n=====PAGE=====\n".join((pg.extract_text() or "") for pg in pdf.pages)
    open(cache, "w", encoding="utf8").write(text)
    return text


def lackawanna_results(path):
    """Lackawanna 'Summary Results Report' PDF: one or two pages per precinct, precinct name on line 4 of each page."""
    precincts, order = {}, []
    for pg in pdf_text(path).split("\n=====PAGE=====\n"):
        lines = pg.splitlines()
        name = lines[3].strip()
        if name not in precincts:
            precincts[name] = {"name": name, "contests": {}}
            order.append(name)
        p, contest = precincts[name], None
        for ln in lines[4:]:
            m = re.match(r"Registered Voters - Total ([\d,]+)", ln)
            if m:
                p["registered"] = num(m.group(1)); continue
            m = re.match(r"Ballots Cast - Total ([\d,]+) ([\d,]+) ([\d,]+)", ln)
            if m:
                p["ballots"], p["eday"], p["mail"] = map(num, m.groups()); continue
            if ln.startswith("Vote For"):
                continue
            m = re.match(r"(.+?) ([\d,]+) ([\d.]+)% ([\d,]+) ([\d,]+) ([\d,]+)$", ln)
            if m and contest:
                if m.group(1) == "Total Votes Cast":
                    contest["total"] = num(m.group(2))
                else:
                    contest["cands"][m.group(1)] = {"v": num(m.group(2)), "ed": num(m.group(4)), "mail": num(m.group(5))}
                continue
            if re.fullmatch(r"[A-Z0-9 .'/&-]+", ln) and not ln.startswith(("TOTAL", "LACKAWANNA PRECINCT")) and ln not in ("YES", "NO"):
                contest = p["contests"].setdefault(ln, {"cands": {}})
                continue
            m = re.match(r"(YES|NO) ([\d,]+) ([\d.]+)% ([\d,]+) ([\d,]+)", ln)
            if m and contest:
                contest["cands"][m.group(1)] = {"v": num(m.group(2)), "ed": num(m.group(4)), "mail": num(m.group(5))}
    out = [precincts[n] for n in order]
    assert len(out) == 163 and all("registered" in p for p in out), "Lackawanna PDF did not parse as expected"
    return out

# Wayne's report has no party labels; map each name to the Lackawanna-style label
WAYNE_CANDS = {
    "JOSH SHAPIRO": "DEM SHAPIRO / DAVIS", "STACY GARRITY": "REP GARRITY / RICHEY",
    "KEN KRAWCHUK": "LIB KRAWCHUK / THOMAS", "PAIGE COGNETTI": "DEM PAIGE COGNETTI",
    "ROB BRESNAHAN JR": "REP ROB BRESNAHAN JR", "BRIAN WRIGHTSON": "DEM BRIAN WRIGHTSON",
    "ROSEMARY BROWN": "REP ROSEMARY BROWN", "JACKIE BAKER": "DEM JACKIE BAKER",
    "LISA BAKER": "REP LISA BAKER", "KYLE DEVLIN": "DEM KYLE DEVLIN",
    "JONATHAN FRITZ": "REP JONATHAN FRITZ", "DOMINIQUE AZZOLLINI": "DEM DOMINIQUE AZZOLLINI",
    "JEFF OLSOMMER": "REP JEFF OLSOMMER", "Write-in": "Write-In Totals",
}


def parse_wayne(path):
    text = pdf_text(path)
    out, p, contest, totals = [], None, None, None
    for ln in text.splitlines():
        if ln.startswith("Precinct "):
            p = {"name": ln[9:].strip(), "contests": {}, "reg": 0, "ballots": 0, "mail": 0}
            out.append(p); contest = None; continue
        if ln == "All Precincts":
            totals = {"contests": {}}; p = totals; continue
        if p is None:
            continue
        m = re.match(r"(.+?) \(Vote for \d+\)$", ln)
        if m:
            contest = p["contests"].setdefault(m.group(1), {}); continue
        m = re.match(r"([\d,]+) ballots .*?, ([\d,]+) registered voters", ln)
        if m and p is not totals:
            b = num(m.group(1))
            if b > p["ballots"]:
                p["ballots"], p["_maxc"] = b, contest
            p["reg"] = num(m.group(2)); continue
        m = re.match(r"(.+?) ([\d,]+) [\d.]+% ([\d,]+) ([\d,]+) ([\d,]+)$", ln)
        if m and contest is not None:
            if m.group(1) == "Total":
                if p is not totals and contest is p.get("_maxc"):
                    p["mail"] = num(m.group(4))
                continue
            contest[WAYNE_CANDS[m.group(1)]] = num(m.group(2))
    for q in out:
        q.pop("_maxc", None)
    # Check precinct sums against the county's own "All Precincts" totals
    for c, cands in totals["contests"].items():
        for k, v in cands.items():
            s = sum(q["contests"].get(c, {}).get(k, 0) for q in out)
            assert s == v, (c, k, s, v)
    return out


def parse_lackawanna(path):
    out = []
    for p in lackawanna_results(path):
        out.append({"name": p["name"], "reg": p["registered"], "ballots": p["ballots"], "mail": p["mail"],
                    "contests": {c: {k: v["v"] for k, v in d["cands"].items()} for c, d in p["contests"].items()}})
    return out


def title(s):
    return re.sub(r"\b([A-Za-z])([A-Za-z']*)", lambda m: m.group(1).upper() + m.group(2).lower(), s)


def muni_lack(n):
    return n.split(" W-")[0]


def muni_wayne(n):
    return title(re.sub(r" #\d+$", "", n))


def key_lack_vtd(n):
    return re.match(r"(.+?)( Ward| District|$)", n).group(1).upper().replace(" ", "")


# Pike's workbook names candidates without party; map to the Lackawanna-style label
PIKE_CANDS = {
    "Shapiro/Davis": "DEM SHAPIRO / DAVIS", "Garrity/Richey": "REP GARRITY / RICHEY",
    "Krawchuk/Thomas": "LIB KRAWCHUK / THOMAS", "Paige Cognetti": "DEM PAIGE COGNETTI",
    "Rob Bresnahan, Jr.": "REP ROB BRESNAHAN JR", "Jackie Baker": "DEM JACKIE BAKER",
    "Lisa Baker": "REP LISA BAKER", "Dominique Azzollini": "DEM DOMINIQUE AZZOLLINI",
    "Jeff Olsommer": "REP JEFF OLSOMMER", "Tarah Probst": "DEM TARAH PROBST",
    "Danica Hartenfels": "REP DANICA HARTENFELS", "Write-in (Total)": "Write-In Totals",
    "YES": "YES", "NO": "NO",
}


# Luzerne lists the Democrat first and the Republican second in every partisan race
# (PA ballot order follows the last governor's race); Watro (116th) ran unopposed as the Republican incumbent.
LUZERNE_CANDS = {
    "Josh Shapiro/Austin Davis": "DEM SHAPIRO / DAVIS", "Stacy Garrity/Jason Richey": "REP GARRITY / RICHEY",
    "Ken Krawchuk/John Thomas": "LIB KRAWCHUK / THOMAS", "Paige Cognetti": "DEM PAIGE COGNETTI",
    "Rob Bresnahan Jr": "REP ROB BRESNAHAN JR", "Rachel Wallace": "DEM RACHEL WALLACE", "Dan Meuser": "REP DAN MEUSER",
    "Jackie Baker": "DEM JACKIE BAKER", "Lisa Baker": "REP LISA BAKER",
    "Marty Flynn": "DEM MARTY FLYNN", "Sharon Soltis Sparano": "REP SHARON SOLTIS SPARANO",
    "Dane Watro": "REP DANE WATRO", "Jeremy Benscoter": "DEM JEREMY BENSCOTER", "Jamie Walsh": "REP JAMIE WALSH",
    "Jim Haddock": "DEM JIM HADDOCK", "John Lombardo": "REP JOHN LOMBARDO",
    "Lauren McCurdy": "DEM LAUREN MCCURDY", "Alec J Ryncavage": "REP ALEC J RYNCAVAGE",
    "Fern Leard": "DEM FERN LEARD", "Brenda Pugh": "REP BRENDA PUGH",
    "Jessica McClay": "DEM JESSICA MCCLAY", "Mike Harostock": "REP MIKE HAROSTOCK",
    "Rejected write-ins": "Write-In Totals", "Unassigned write-ins": "Write-In Totals",
    "Yes": "YES", "No": "NO",
}


def ordinal(n):
    return n + ("TH" if n[-2:] in ("11", "12", "13") else {"1": "ST", "2": "ND", "3": "RD"}.get(n[-1], "TH"))


def contest_name(s):
    """Normalize to Lackawanna's contest names, e.g. 'REPRESENTATIVE IN CONGRESS DIST 8 ( 1)' or
    'Representative in Congress 8th Congressional District (Vote For 1)' -> 'REPRESENTATIVE IN CONGRESS 8TH DISTRICT'"""
    s = re.sub(r"\s*\((\s*\d+|Vote For \d+)\)$", "", s.strip())
    s = re.sub(r"\s+", " ", s).upper().replace("GOVERNOR/LIEUTENANT GOVERNOR", "GOVERNOR AND LIEUTENANT GOVERNOR")
    s = re.sub(r"DIST (\d+)$", lambda m: ordinal(m.group(1)) + " DISTRICT", s)
    return re.sub(r"(\d+)(ST|ND|RD|TH) (CONGRESSIONAL|SENATORIAL|LEGISLATIVE) DISTRICT", r"\1\2 DISTRICT", s)


def parse_clarity(path, cands, keep=None, drop=()):
    """Clarity 'detail.xlsx': one sheet per contest, 4 columns per choice (vote types + Total Votes).
    keep(name, contests) filters precincts; contests whose name is in drop are left out."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    for r in list(wb["Registered Voters"].iter_rows(values_only=True))[1:]:
        if r[0] and r[0] != "Total:":
            out[r[0]] = {"name": re.sub(r"\s+", " ", r[0]), "reg": r[1], "ballots": r[2], "mail": 0, "contests": {}, "_best": 0}
    for ws in wb.worksheets[2:]:
        rows = list(ws.iter_rows(values_only=True))
        cname = contest_name(rows[0][0])
        heads, sub = rows[1], rows[2]
        cols = [(i, cands[heads[i]]) for i in range(2, len(heads)) if heads[i]]
        mail_off = next(j for j in range(3) if sub[2 + j].lower().startswith("mail"))
        tot = {}
        for r in rows[3:]:
            if not r[0]:
                continue
            votes = {}
            for i, lab in cols:
                votes[lab] = votes.get(lab, 0) + r[i + 3]
            if r[0] == "Total:":
                tot = votes
                continue
            p = out[r[0]]
            p["contests"][cname] = votes
            total = sum(votes.values())
            if total > p["_best"]:   # mail ballots ~ mail-in votes in the busiest contest
                p["_best"], p["mail"] = total, sum(r[i + mail_off] for i, _ in cols)
        for lab, v in tot.items():
            assert sum(p["contests"].get(cname, {}).get(lab, 0) for p in out.values()) == v, (cname, lab)
    res = []
    for p in out.values():
        p.pop("_best")
        if keep and not keep(p["name"], p["contests"]):
            continue
        p["contests"] = {k: v for k, v in p["contests"].items() if k not in drop}
        res.append(p)
    return res


def parse_pike(path):
    return parse_clarity(path, PIKE_CANDS)


def parse_luzerne(path):
    # Luzerne is split between PA-8 and PA-9: keep precincts with PA-8 votes, drop the PA-9 race
    res = parse_clarity(path, LUZERNE_CANDS, keep=lambda n, c: "REPRESENTATIVE IN CONGRESS 8TH DISTRICT" in c,
                        drop=("REPRESENTATIVE IN CONGRESS 9TH DISTRICT",))
    for p in res:
        if p["name"] == "Butler Township Dist 05":
            p["split"] = "Split between PA-8 and PA-9. The U.S. House result counts only the PA-8 part; other races cover the whole precinct."
    return res


def luzerne_key(n):
    m = re.match(r"(.+?) (Boro|City|Township)(?: (Ward|Dist) (\d+)| (\d+))?$", n)
    base, kind, unit, num, bare = m.groups()
    base = base.upper()
    if n == "Plymouth Township":
        return "PLYMOUTH DISTRICT 01"
    if kind == "Township" and base == "WILKES-BARRE":
        return f"WILKES-BARRE TWP WARD {num}"
    if bare:   # "Pittston Township 01"
        return f"{base} DISTRICT {bare}"
    if num:
        return f"{base} {'WARD' if unit == 'Ward' else 'DISTRICT'} {num}"
    return base


def luzerne_vtd_key(rec, recs):
    n = re.sub(r" \(.*\)$", "", rec["NAME20"])   # "HAZLE DISTRICT 01 (CD 08)", "BUTLER DISTRICT 02 (UPPER LEHIGH)"
    if n in ("WILKES-BARRE WARD 01", "WILKES-BARRE WARD 02"):
        # the city's wards come first in VTD order; the second pair belongs to Wilkes-Barre Township
        same = [r for r in recs if r["NAME20"] == rec["NAME20"]]
        if rec is same[1]:
            return n.replace("WILKES-BARRE", "WILKES-BARRE TWP")
    return n


def muni_luzerne(n):
    return re.sub(r" (Ward|Dist) \d+$| \d+$", "", n).replace(" Boro", " Borough")


def pike_key(n):
    n = re.sub(r"\s+", " ", n)
    m = re.match(r"(.+?) (TWP|BORO)(?: #(\d+))?$", n)
    base, kind, d = m.groups()
    if base == "MILFORD":
        return f"MILFORD {kind}"
    return base + (f" DISTRICT {int(d):02d}" if d else "")


def pike_vtd_key(rec, recs):
    n = rec["NAME20"]
    if n == "MILFORD":   # two VTDs share the name; the borough is the small one
        other = min(r["ALAND20"] for r in recs if r["NAME20"] == "MILFORD")
        return "MILFORD BORO" if rec["ALAND20"] == other else "MILFORD TWP"
    if n.startswith("MATAMORAS"):   # two 2020 VTDs, one 2026 precinct
        return "MATAMORAS"
    return n


MONROE_CANDS = {"JOSH SHAPIRO": "DEM SHAPIRO / DAVIS", "STACY GARRITY": "REP GARRITY / RICHEY",
                "KEN KRAWCHUK": "LIB KRAWCHUK / THOMAS", "Write-in": "Write-In Totals"}
PARTY = {"DEMOCRATIC": "DEM", "REPUBLICAN": "REP", "LIBERTARIAN": "LIB"}
# 2026 precincts drawn since 2020 with no public boundary, grouped so each group matches one 2020 Census district:
# Middle Smithfield One+Two were cut from the West district and Three+Four from the East (state file VTD codes),
# Tunkhannock East+West from the single 2020 district. (label, municipality, precinct parts, 2022 DOS precinct codes)
MONROE_COMBINE = [
    ("Middle Smithfield West", "Middle Smithfield", ["One", "Two"], {"2022": [176]}),
    ("Middle Smithfield East", "Middle Smithfield", ["Three", "Four"], {"2022": [173]}),
    ("Tunkhannock", "Tunkhannock", ["East", "West"], None),
]
COMBINED = {f"{label} ({len(parts)} precincts)": parts for label, _, parts, _ in MONROE_COMBINE}
WORDNUM = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7,
           "First": 1, "Second": 2, "Third": 3, "Fourth": 4, "Fifth": 5, "Sixth": 6}


def parse_monroe(html_dir):
    """Monroe's results site: one page per contest, each with a 'View Results by District' precinct table.
    No precinct registration or ballot counts are published, so reg/ballots/mail stay None."""
    import glob, html as H
    out = {}
    for f in sorted(glob.glob(os.path.join(html_dir, "c_*.html"))):
        h = open(f, encoding="utf8").read()
        cname = re.sub(r"\+", " ", os.path.basename(f)[2:-5])
        if cname == "REPRESENTATIVE IN CONGRESS 7TH DISTRICT":
            continue
        party = {n.strip(): PARTY[p] for n, p in re.findall(r"<b>\s*([^<]+?)</b>\s*<i class=\"color-\w+\">\(([A-Z]+)\)", h)}
        total = int(re.search(r"<td>Total</td><td>(\d+)</td>", h).group(1))
        seg = h[h.find("View Results by District"):]
        heads = [H.unescape(x).strip() for x in re.findall(r"<th>(.*?)</th>", seg[:3000], re.S)][1:]
        labels = [MONROE_CANDS.get(n) or f"{party.get(n, 'LIB')} {n}" for n in heads]
        rows = re.findall(r"<tr>\s*<td>([^<]+)</td>((?:\s*<td>\d+</td>)+)\s*</tr>", seg)
        s = 0
        for name, cells in rows:
            votes = [int(v) for v in re.findall(r"\d+", cells)]
            p = out.setdefault(name.strip(), {"name": name.strip(), "reg": None, "ballots": None, "mail": None, "contests": {}})
            p["contests"][cname] = dict(zip(labels, votes))
            s += sum(votes)
        assert s == total, (cname, s, total)
    # PA-8 precincts only
    res = [p for p in out.values() if "REPRESENTATIVE IN CONGRESS 8TH DISTRICT" in p["contests"]]
    for label, muni, parts, past in MONROE_COMBINE:
        group = [p for p in res if p["name"] in [f"{muni} {x}" for x in parts]]
        assert len(group) == len(parts), label
        merged = {"name": f"{label} ({len(parts)} precincts)", "reg": None, "ballots": None, "mail": None, "contests": {},
                  "split": f"Combines {muni} precincts {' and '.join(parts)}, which together cover one 2020 Census district; "
                           "the county has not published their separate boundaries.",
                  **({"past_codes": past} if past else {})}
        for p in group:
            for c, v in p["contests"].items():
                d = merged["contests"].setdefault(c, {})
                for k, n in v.items():
                    d[k] = d.get(k, 0) + n
        res = [p for p in res if p not in group] + [merged]
    for p in res:
        if p["name"] == "Ross Two":
            p["split"] = ("Ross One votes in PA-7. Its shape here is Ross Township cut along the PA-8 line, "
                          "since the county has not published the new precinct boundary.")
    return res


def monroe_key(n):
    m = re.match(r"(.+?) \((\d) precincts\)$", n)
    if m:
        return m.group(1).upper()
    m = re.match(r"(East Stroudsburg|Stroudsburg) (\w+) Ward$", n)
    if m:
        return f"{m.group(1).upper()} {'DISTRICT' if m.group(1) == 'East Stroudsburg' else 'WARD'} {WORDNUM[m.group(2)]:02d}"
    m = re.match(r"(.+?) (One|Two|Three|Four|Five|Six|Seven)$", n)
    if m:
        return "ROSS" if m.group(1) == "Ross" else f"{m.group(1).upper()} DISTRICT {WORDNUM[m.group(2)]:02d}"
    m = re.match(r"(.+?) (North|South|Northern|Southern|Eastern|Western)$", n)
    if m:
        return f"{m.group(1).upper()} DISTRICT {m.group(2).upper().replace('ERN', '')}"
    return n.upper()


def monroe_vtd_key(rec, recs):
    n = re.sub(r" \(CD 0\d\)$", "", rec["NAME20"])   # SMITHFIELD DISTRICT 01 (CD 07)/(CD 08) -> one precinct now
    return re.sub(r"^(MIDDLE SMITHFIELD) DISTRICT (EAST|WEST)$", r"\1 \2", n)


def muni_monroe(n):
    return re.sub(r"( East| West)? \(\d precincts\)$| (One|Two|Three|Four|Five|Six|Seven|North|South|Northern|Southern|Eastern|Western)$"
                  r"| (First|Second|Third|Fourth|Fifth|Sixth) Ward$", "", n)


def by_order(check):
    def match(res, srs):
        assert len(srs) == len(res), (len(srs), len(res))
        for sr, p in zip(srs, res):
            assert check(p["name"], sr.record["NAME20"]), (p["name"], sr.record["NAME20"])
        return [(p, [sr]) for sr, p in zip(srs, res)]
    return match


def by_key(pkey, vkey, partial=False):
    """partial=True: the county is split, so VTDs with no kept precinct are expected (and listed)."""
    def match(res, srs):
        recs = [sr.record for sr in srs]
        groups = {}
        for sr in srs:
            groups.setdefault(vkey(sr.record, recs), []).append(sr)
        pairs = [(p, groups.pop(pkey(p["name"]))) for p in res]
        if partial:
            print("  left out:", sorted(groups))
        else:
            assert not groups, ("unmatched VTDs", list(groups))
        return pairs
    return match


COUNTIES = [
    # name, fips, results loader, results path, display name fn, muni fn, precinct<->VTD matcher
    ("Lackawanna", "069", parse_lackawanna, os.path.join(COUNTY_DIR, "lackawanna", "G26.PCT12.pdf"), lambda n: n, muni_lack,
     by_order(lambda p, v: re.sub(r" (Township|Twp\.)$", "", muni_lack(p)).upper().replace(" ", "") == key_lack_vtd(v))),
    ("Wayne", "127", parse_wayne, os.path.join(COUNTY_DIR, "wayne", "statement-of-votes-2026-general.pdf"), title, muni_wayne,
     by_order(lambda p, v: re.sub(r" (TOWNSHIP|BOROUGH)( #\d+)?$", "", p) == re.sub(r" DISTRICT \d+$", "", v))),
    ("Pike", "103", parse_pike, os.path.join(COUNTY_DIR, "pike", "detail.xlsx"),
     lambda n: title(n).replace(" Twp", " Township").replace(" Boro", " Borough"),
     lambda n: title(re.sub(r" #\d+$", "", n)).replace(" Twp", " Township").replace(" Boro", " Borough"),
     by_key(pike_key, pike_vtd_key)),
    ("Luzerne", "079", parse_luzerne, os.path.join(COUNTY_DIR, "luzerne", "detail.xlsx"),
     lambda n: n.replace(" Boro", " Borough"), muni_luzerne,
     by_key(luzerne_key, luzerne_vtd_key, partial=True)),
    ("Monroe", "089", parse_monroe, os.path.join(COUNTY_DIR, "monroe"), lambda n: n, muni_monroe,
     by_key(monroe_key, monroe_vtd_key, partial=True)),
]


def pa8_shape():
    from shapely.geometry import shape
    r = shapefile.Reader(os.path.join(CENSUS_DIR, "tl_2022_42_cd118"))
    return next(shape(sr.shape.__geo_interface__) for sr in r.shapeRecords() if sr.record["CD118FP"] == "08")
YEAR = "2026"


def rnd(coords):
    return [[round(x, 5), round(y, 5)] for x, y in coords]


def geometry(srs, clip=None):
    """clip: shapely geometry to intersect with (drops slivers under 2% of the result)."""
    g = srs[0].shape.__geo_interface__
    if len(srs) > 1 or clip is not None:
        from shapely.geometry import shape, mapping, MultiPolygon
        from shapely.ops import unary_union
        u = unary_union([shape(sr.shape.__geo_interface__) for sr in srs])
        if clip is not None:
            u = u.intersection(clip)
            parts = list(getattr(u, "geoms", [u]))
            parts = [q for q in parts if q.geom_type == "Polygon" and q.area > 0.02 * u.area]
            u = parts[0] if len(parts) == 1 else MultiPolygon(parts)
        g = mapping(u)
    if g["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [rnd(r) for r in g["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[rnd(r) for r in poly] for poly in g["coordinates"]]}


# --- Party registration: PA Department of State precinct file (2026 General Primary rolls) ---
DOS_COUNTY = {"Lackawanna": "35", "Luzerne": "40", "Monroe": "45", "Pike": "52", "Wayne": "64"}
TYPE = {"City": "2", "Township": "4", "Twp": "4", "Twp.": "4", "TOWNSHIP": "4", "TWP": "4",
        "Boro": "6", "BORO": "6", "BOROUGH": "6"}
WORDS = {"NE": "NORTHEAST", "NW": "NORTHWEST", "SO": "SOUTH", "NORTHERN": "NORTH", "SOUTHERN": "SOUTH",
         "EASTERN": "EAST", "WESTERN": "WEST"}


def mkey(name):
    return re.sub(r"[ .]", "", name.upper()).replace("MT", "MOUNT", 1) if name.upper().startswith("MT.") \
        else re.sub(r"[ .]", "", name.upper())


def unit(tok):
    tok = tok.upper()
    return int(tok) if tok.isdigit() else WORDS.get(tok, tok)


def load_registration(path):
    """(county, muni key) -> list of (type code, units tuple, CD, {D,R,L,O})"""
    import csv
    reg = {}
    code2county = {v: k for k, v in DOS_COUNTY.items()}
    for r in csv.reader(open(path)):
        if r[2] not in code2county:
            continue
        muni = re.sub(r"\s*\(USC \d+\)|\s+School District \d+", "", r[26]).strip()
        # East Stroudsburg rows carry an old "11TH CONGRESSIONAL" label in the second breakdown; it is not a precinct part
        units = tuple(unit(re.sub(r"\s*\(USC \d+\)", "", n).strip()) for n in (r[28], r[30])
                      if n.strip() and "CONGRESSIONAL" not in n)
        counts = {"D": int(r[6]), "R": int(r[9]), "L": int(r[12]), "O": int(r[15]) + int(r[18]) + int(r[21])}
        # (type code, units, CD, counts, DOS precinct code, MCD code)
        reg.setdefault((code2county[r[2]], mkey(muni)), []).append((r[25], units, r[22], counts, int(r[3]), int(r[32])))
    return reg


def precinct_regkey(county, name):
    """Results precinct name -> (muni key, type code or None, units tuple, or 'ALL' for combined precincts)"""
    if county == "Lackawanna":
        m = re.match(r"(.+?) W-(\d+) P-(\S+)$", name)
        muni, w, p = m.groups()
        t = None
        mt = re.match(r"(.+?) (Township|Twp\.)$", muni)
        if mt:
            muni, t = mt.group(1), "4"
        units = ([int(w)] if w != "00" else []) + ([] if p == "00" else [unit(x) for x in p.split("-")])
        return mkey(muni), t, tuple(units)
    if county in ("Wayne", "Pike"):
        m = re.match(r"(.+?) +(TOWNSHIP|BOROUGH|TWP|BORO)(?: #(\d+))?$", name)
        return mkey(m.group(1)), TYPE[m.group(2)], ((int(m.group(3)),) if m.group(3) else ())
    if county == "Luzerne":
        m = re.match(r"(.+?) (Boro|City|Township)(?: (?:Ward|Dist) (\d+)| (\d+))?$", name)
        n = m.group(3) or m.group(4)
        return mkey(m.group(1)), TYPE[m.group(2)], ((int(n),) if n else ())
    if county == "Monroe":
        if name in COMBINED:
            muni = re.sub(r" (East|West)$", "", re.sub(r" \(\d precincts\)$", "", name)) if name.startswith("Middle") else name.split(" (")[0]
            return mkey(muni), None, [(WORDNUM[x],) if x in WORDNUM else (unit(x),) for x in COMBINED[name]]
        if name == "Ross Two":
            return "ROSS", None, ()
        m = re.match(r"(.+?) (\w+) Ward$", name) or re.match(r"(.+?) (One|Two|Three|Four|Five|Six|Seven|North|South|Northern|Southern|Eastern|Western|East|West)$", name)
        if m:
            return mkey(m.group(1)), None, (WORDNUM[m.group(2)] if m.group(2) in WORDNUM else unit(m.group(2)),)
        return mkey(name), None, ()


def registration_for(reg, county, name):
    muni, t, units = precinct_regkey(county, name)
    rows = reg.get((county, muni), [])
    if county == "Monroe":
        rows = [r for r in rows if r[2] == "8"]   # Monroe's PA-7 rows (Ross One) stay out
    if isinstance(units, list):   # combined precinct: the rows for each of its parts
        rows = [r for r in rows if r[1] in units]
    else:
        rows = [r for r in rows if r[1] == units and (t is None or r[0] == t)]
    assert rows, (county, name, muni, t, units)
    assert len({r[0] for r in rows}) == 1, ("ambiguous type", county, name)
    out = {"D": 0, "R": 0, "L": 0, "O": 0}
    for r in rows:
        for k in out:
            out[k] += r[3][k]
    return out, sorted({r[4] for r in rows}), rows[0][5]


REG = load_registration(os.path.join(STATE_DIR, "vr2026p.txt"))

feats = []
for county, fips, loader, path, disp, muni, match in COUNTIES:
    res = loader(path)
    srs = shapefile.Reader(os.path.join(CENSUS_DIR, f"tl_2020_42{fips}_vtd20")).shapeRecords()
    for p, group in match(res, srs):
        clip = pa8_shape() if (county, p["name"]) == ("Monroe", "Ross Two") else None
        pr, codes, mcd = registration_for(REG, county, p["name"])
        if p["reg"]:   # sanity check against the county's own November registration count
            ratio = sum(pr.values()) / p["reg"]
            if not 0.85 < ratio < 1.15:
                print(f"  check {county} {p['name']}: state {sum(pr.values())} vs county {p['reg']}")
        feats.append({"type": "Feature", "geometry": geometry(group, clip), "properties": {
            "name": disp(p["name"]), "county": county, "muni": muni(p["name"]),
            "reg": p["reg"], "ballots": p["ballots"], "mail": p["mail"], "y": {YEAR: p["contests"]}, "pr": pr,
            "codes": codes, "mcd": mcd,
            **({"note": p["split"]} if "split" in p else {}),
            **({"past_codes": p["past_codes"]} if "past_codes" in p else {})}})
    print(county, len(res), "precincts")

# Every PA-8 registration row should land on exactly one mapped precinct
used = sum(sum(f["properties"]["pr"].values()) for f in feats)
pa8_rows = sum(sum(r[3].values()) for rows in REG.values() for r in rows if r[2] == "8")
print("registration on map", used, "| state file PA-8 rows", pa8_rows)

# --- 2024 general: PA DOS precinct returns + precinct registration, joined by DOS precinct code ---
OFFICES = {"USP": "PRESIDENT OF THE UNITED STATES", "USS": "UNITED STATES SENATOR", "ATT": "ATTORNEY GENERAL",
           "AUD": "AUDITOR GENERAL", "TRE": "STATE TREASURER", "GOV": "GOVERNOR AND LIEUTENANT GOVERNOR"}


def load_returns(path, mcds=None, cds=None):
    """(county code, precinct code) -> {contest: {candidate label: votes}}.
    mcds/cds, when given, collect each precinct's MCD code and congressional district."""
    import csv
    out = {}
    for r in csv.reader(open(path)):
        if r[2] not in DOS_COUNTY.values():
            continue
        if mcds is not None:
            mcds.setdefault((r[2], int(r[28])), set()).add(int(r[3]))
            cds[(r[2], int(r[3]))] = r[18]
        office, dist = r[8], r[5]
        if office in OFFICES:
            cname = OFFICES[office]
        elif office == "USC":
            if dist != "8":   # Luzerne's and Monroe's other congressional races stay off the PA-8 map
                continue
            cname = f"REPRESENTATIVE IN CONGRESS {ordinal(dist)} DISTRICT"
        elif office == "STS":
            cname = f"SENATOR IN THE GENERAL ASSEMBLY {ordinal(dist)} DISTRICT"
        elif office == "STH":
            cname = f"REPRESENTATIVE IN THE GENERAL ASSEMBLY {ordinal(dist)} DISTRICT"
        else:
            continue
        label = f"{r[9].strip()} {r[12].strip()} {r[11].strip()}".upper()
        c = out.setdefault((r[2], int(r[3])), {}).setdefault(cname, {})
        c[label] = c.get(label, 0) + int(r[15])
    return out


def load_reg_by_code(path):
    import csv
    out = {}
    for r in csv.reader(open(path)):
        if r[2] in DOS_COUNTY.values():
            n = {r[5]: int(r[6]), r[8]: int(r[9]), r[11]: int(r[12]), r[14]: int(r[15]), r[17]: int(r[18]), r[20]: int(r[21])}
            out[(r[2], int(r[3]))] = {"D": n.get("DEM", 0), "R": n.get("REP", 0), "L": n.get("LIB", 0),
                                      "O": sum(v for k, v in n.items() if k not in ("DEM", "REP", "LIB"))}
    return out


def attach_year(yr, returns_path, reg_path, top_contest):
    """Join a past general election to the 2026 precincts by DOS precinct code.
    A 2026 precinct whose codes did not exist that year must be the only mapped precinct in its municipality
    (Monroe's Middle Smithfield and Tunkhannock); it then takes the whole municipality's PA-8 precincts."""
    mcds, cds = {}, {}
    ret = load_returns(returns_path, mcds, cds)
    reg = load_reg_by_code(reg_path)
    per_mcd = {}
    for f in feats:
        per_mcd.setdefault((DOS_COUNTY[f["properties"]["county"]], f["properties"]["mcd"]), []).append(f)
    for (cc, mcd), group in per_mcd.items():
        if any(yr in f["properties"].get("past_codes", {}) for f in group):
            fixed = {c for f in group for c in f["properties"]["past_codes"][yr]}
            assert fixed == {c for c in mcds[(cc, mcd)] if cds[(cc, c)] == "8"}, (yr, mcd, fixed)
            print(f"  {yr}: " + ", ".join(f"{f['properties']['name']} uses {f['properties']['past_codes'][yr]}" for f in group))
        mapped = {c for f in group for c in f["properties"]["codes"]}
        extra = {c for c in mcds.get((cc, mcd), set()) - mapped if cds[(cc, c)] == "8"}
        missing = mapped - mcds.get((cc, mcd), set())
        if (missing or extra) and not any(yr in f["properties"].get("past_codes", {}) for f in group):
            assert len(group) == 1, (yr, cc, mcd, sorted(missing), sorted(extra))
            print(f"  {yr}: {group[0]['properties']['name']} uses whole-municipality codes {sorted(mapped - missing | extra)}")
        for f in group:
            p = f["properties"]
            codes = (p["past_codes"][yr] if yr in p.get("past_codes", {})
                     else p["codes"] if not (missing or extra) else sorted(mapped - missing | extra))
            contests, pr = {}, {"D": 0, "R": 0, "L": 0, "O": 0}
            for code in codes:
                for cname, cands in ret[(cc, code)].items():
                    d = contests.setdefault(cname, {})
                    for k, v in cands.items():
                        d[k] = d.get(k, 0) + v
                for k, v in reg[(cc, code)].items():
                    pr[k] += v
            p["y"][yr] = contests
            # past-year ballots are not in the state file; votes in the top race stand in for ballots cast
            p["past"] = p.get("past", {})
            p["past"][yr] = {"reg": sum(pr.values()), "ballots": sum(contests[top_contest].values()), "pr": pr}
    house = "REPRESENTATIVE IN CONGRESS 8TH DISTRICT"
    tot = {}
    for f in feats:
        for k, v in f["properties"]["y"][yr].get(house, {}).items():
            tot[k] = tot.get(k, 0) + v
    print(f"{yr} PA-8 House:", tot)


attach_year("2024", os.path.join(STATE_DIR, "er2024g.txt"), os.path.join(STATE_DIR, "vr2024g.txt"), "PRESIDENT OF THE UNITED STATES")
attach_year("2022", os.path.join(STATE_DIR, "er2022g.txt"), os.path.join(STATE_DIR, "vr2022g.txt"), "GOVERNOR AND LIEUTENANT GOVERNOR")


# State Senate and State House districts for every precinct (not just those with a 2026 race), from the DOS file
def legislative_districts(path):
    import csv
    return {(r[2], int(r[3])): (int(r[23]), int(r[24])) for r in csv.reader(open(path)) if r[2] in DOS_COUNTY.values()}


LD = legislative_districts(os.path.join(STATE_DIR, "vr2026p.txt"))
for f in feats:
    p = f["properties"]
    sds = {LD[(DOS_COUNTY[p["county"]], c)][0] for c in p["codes"]}
    assert len(sds) == 1, (p["name"], sds)
    p["sd"] = sds.pop()
    # a combined precinct (Middle Smithfield) can span two House districts, so this is a list
    p["hd"] = sorted({LD[(DOS_COUNTY[p["county"]], c)][1] for c in p["codes"]})

s = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write(s)
print(len(feats), "features,", len(s), "bytes")
