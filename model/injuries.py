"""Convert a Covers.com injury scrape ({school: [[name, pos, status], ...]}) to the model's format, keyed by dashboard names."""
import json, sys
ALIAS = {"Mississippi": "Ole Miss", "North Carolina State": "NC State", "Hawai'i": "Hawaii", "Louisiana-Monroe": "UL Monroe", "UMass": "Massachusetts",
         "San José State": "San Jose State"}
def convert(raw, source):
    return {"source": source, "teams": {ALIAS.get(k, k): [{"n": n, "pos": p, "st": s} for n, p, s in v] for k, v in raw.items()}}
if __name__ == "__main__":
    src, dst, label = sys.argv[1], sys.argv[2], sys.argv[3]
    json.dump(convert(json.load(open(src)), label), open(dst, "w"), indent=0)
