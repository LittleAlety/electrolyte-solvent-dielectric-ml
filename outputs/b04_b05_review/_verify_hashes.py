import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def h(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


checks = []
for man in ["outputs/b05/E1_structure_vs_electronic/e1_manifest.json",
            "outputs/b05/E4_domain_generalization/e4_manifest.json",
            "outputs/b05/E6_screening_decisions/e6_manifest.json"]:
    m = json.loads((ROOT / man).read_text(encoding="utf-8"))
    for k, v in m.get("outputs", {}).items():
        p = v["path"].replace("\\", "/")
        checks.append((h(p) == v["sha256"], "out:" + k, p))
    for k, v in m.get("inputs", {}).items():
        if "path" not in v:
            continue
        p = v["path"].replace("\\", "/")
        if (ROOT / p).is_file():
            checks.append((h(p) == v["sha256"], "in:" + k, p))

for ok, k, p in checks:
    print(("OK  " if ok else "FAIL"), k, p)
bad = [c for c in checks if not c[0]]
print()
print(f"{len(checks)-len(bad)}/{len(checks)} hashes verify")
print("EVIDENCE UNMODIFIED" if not bad else f"MODIFIED: {bad}")
