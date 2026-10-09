"""Convert a Covers.com injury scrape ({school: [[name, pos, status(, since)], ...]}) to the model's format, keyed by dashboard names."""
import json, sys
# Covers' team labels (logo alt text) -> dashboard names
ALIAS = {"Mississippi": "Ole Miss", "North Carolina State": "NC State", "Hawai'i": "Hawaii", "Louisiana-Monroe": "UL Monroe", "UMass": "Massachusetts",
         "San José State": "San Jose State", "MS State": "Mississippi State", "ND State": "North Dakota State", "FIU Panthers": "Florida International",
         "JSU": "Jacksonville State", "NIU": "Northern Illinois"}
def convert(raw, source):
    return {"source": source, "teams": {ALIAS.get(k, k): [{"n": r[0], "pos": r[1], "st": r[2], **({"since": r[3]} if len(r) > 3 and r[3] else {})} for r in v] for k, v in raw.items()}}
def apply_overrides(doc, ov):
    """Replace or add rows from a verified-overrides file ({teams: {dashboard name: [{n, pos, st, since, source}]}})."""
    k = lambda n: (n.split()[0][0].lower() if n else "", n.split()[-1].lower() if n else "")
    for team, rows in (ov.get("teams") or {}).items():
        cur = doc["teams"].setdefault(team, [])
        for r in rows:
            cur[:] = [x for x in cur if k(x["n"]) != k(r["n"])] + [{**r, "override": True}]
    return doc


if __name__ == "__main__":
    src, dst, label = sys.argv[1], sys.argv[2], sys.argv[3]
    doc = convert(json.load(open(src)), label)
    if len(sys.argv) > 4:  # optional verified overrides, e.g. data/<year>/injury_overrides.json
        doc = apply_overrides(doc, json.load(open(sys.argv[4])))
    json.dump(doc, open(dst, "w"), indent=0)
