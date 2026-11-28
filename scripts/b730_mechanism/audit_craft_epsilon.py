#!/usr/bin/env python
"""B730-01: recover CRAFT-epsilon for audit and record its exact version.

CRAFT-epsilon (arXiv 2610.28850, MIT licence) is close enough to this project's
question that it must be read on its own terms rather than through an abstract.
This script pins the repository to the commit whose message says it applies the
paper's V_m(T) correction, records every file's SHA256, and extracts the parts
that matter for comparison:

  * the 41 fitted parameters (so the model can be re-run without importing it)
  * the epsilon_from_record formula (Clausius-Mossotti eps_inf + Onsager-
    Kirkwood-Froehlich orientation term)
  * the molar-volume group contributions (Bouteloup & Mathieu 2019)
  * the reference predictions for 16 liquids, which are the acceptance test

What is NOT done: the source is not copied into the repo as importable code.
Only the files needed to audit the model definition are stored under
data/external_raw/craft_epsilon/ as read-only evidence, consistent with MIT.

Outputs (outputs/b730_mechanism/craft_comparison/):
  craft_provenance.json
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEST = REPO_ROOT / "data" / "external_raw" / "craft_epsilon"
OUT = REPO_ROOT / "outputs" / "b730_mechanism" / "craft_comparison"
GEN = "recover_craft_epsilon/1.0.0"

OWNER_REPO = "simonmb/craft-epsilon"
COMMIT = "65fa0fb0a55838a656769ed717d41d52f1516c4a"
FILES = [
    "README.md",
    "LICENSE",
    "craft_epsilon/model.py",
    "craft_epsilon/parameters.py",
    "craft_epsilon/constants.py",
    "craft_epsilon/molar_volume.py",
    "craft_epsilon/descriptors.py",
    "craft_epsilon/groups.py",
    "craft_epsilon/__init__.py",
    "tests/data/reference.json",
]


def fetch(path: str) -> bytes:
    url = (f"https://api.github.com/repos/{OWNER_REPO}/contents/{path}"
           f"?ref={COMMIT}")
    r = subprocess.run(["curl", "-sS", "-m", "120", url], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed for {path}: {r.stderr[:200]!r}")
    d = json.loads(r.stdout.decode("utf-8"))
    if "content" not in d:
        raise RuntimeError(f"no content for {path}: {str(d)[:200]}")
    return base64.b64decode(d["content"])


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_parameters(src: str) -> dict:
    """Load the 41 parameters by executing only the PARAMETERS literal."""
    ns = {}
    start = src.index("PARAMETERS = {")
    depth = 0
    i = start + len("PARAMETERS = ")
    j = i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    lit = src[i:j + 1]
    exec("PARAMETERS = " + lit, ns)   # noqa: S102 - audit of a pinned literal
    return ns["PARAMETERS"]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    DEST.mkdir(parents=True, exist_ok=True)

    files = {}
    blobs = {}
    for rel in FILES:
        data = fetch(rel)
        blobs[rel] = data
        name = rel.replace("craft_epsilon/", "").replace("tests/data/", "tests_data_")
        name = name.replace(".py", ".py").replace("/", "_")
        p = DEST / name
        p.write_bytes(data)
        files[rel] = {
            "saved_as": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
            "bytes": len(data), "sha256": sha(data),
        }
        print(f"  {rel:34s} {len(data):>8d}  {files[rel]['sha256'][:16]}")

    params = parse_parameters(blobs["craft_epsilon/parameters.py"].decode("utf-8"))
    n_params = (len(params["nonpolar"]["atom_group_scales"]) + 1
                + len(params["polar"]["atom_group_scales"])
                + len(params["polar"]["family_scales"]) + 1
                + len(params["hbond"]["fragment_scales"]) + 2)
    reference = json.loads(blobs["tests/data/reference.json"].decode("utf-8"))

    doc = {
        "schema": "b730.craft_provenance/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": GEN,
        "repository": f"https://github.com/{OWNER_REPO}",
        "pinned_commit": COMMIT,
        "commit_date": "2026-10-19T23:06:54Z",
        "commit_message": "Apply the paper's V_m(T) correction in epsilon_from_record",
        "licence": "MIT",
        "paper": "arXiv 2610.28850",
        "zenodo_doi": "10.5281/zenodo.23485587",
        "files": files,
        "use_policy": (
            "MIT permits reuse with attribution. The model is re-implemented from "
            "the stored definitions rather than imported, so this project does not "
            "vendor the package; the stored copies are read-only audit evidence."
        ),
        "model_definition_extracted": {
            "n_fitted_parameters": n_params,
            "n_fitted_parameters_declared_by_author": 41,
            "stages": {
                "nonpolar": "3 params: 2 atom-group scales + 1 dipole scale",
                "polar": "21 params: 11 atom-group + 9 family scales + 1 rest scale",
                "hbond": "17 params: 15 fragment scales + 1 rare scale + 1 rest scale",
            },
            "epsilon_inf_model": (
                "Clausius-Mossotti with atom-group-scaled, Boltzmann-averaged atomic "
                "polarizabilities: x = 4pi/3 * N_A * alpha_scaled[A^3] * 1e-24 / V_m, "
                "eps_inf = (1+2x)/(1-x), x capped at 0.99"
            ),
            "orientation_model": (
                "Onsager-Kirkwood-Froehlich: a = N_A mu_eff^2 D^2 / (9 eps0 kB T V_m), "
                "b = eps_inf + a (eps_inf+2)^2, eps = (b + sqrt(b^2 + 8 eps_inf^2))/4"
            ),
            "effective_dipole": (
                "mu_eff = b*mu_remainder + sum_k c_k * mu_k, Boltzmann mean square; "
                "group dipoles built from charges x positions + atomic dipoles"
            ),
            "molar_volume": (
                "Bouteloup & Mathieu 2019 group contributions (smi2DC), at 298.15 K, "
                "with a FIXED alpha_V = 1e-3 K^-1 for temperature correction"
            ),
            "conformer_protocol": "RDKit ETKDGv3, GFN2-xTB/ALPB(diethyl ether), qRRHO weights",
            "temperature": "298.15 K only",
        },
        "reference_predictions": {
            "n_liquids": len(reference),
            "note": ("author's own stored values for 16 liquids; used as the acceptance "
                     "test of any re-implementation"),
            "examples": {k: {"name": v["name"], "class": v["class"],
                             "epsilon_paper": v["epsilon_paper"]}
                         for k, v in list(reference.items())[:6]},
        },
        "reproducibility_caveats_from_author": [
            "conformer ensembles depend slightly on RDKit version and platform",
            "predictions can deviate from the paper by a few per cent for small rings and diols",
            "xtb 6.7.1 was used to fit; a different xtb changes conformers",
        ],
        "what_this_repo_cannot_reproduce": (
            "The 1393-liquid training set is not shipped: only 16 reference ensembles are "
            "included. So the FIT cannot be reproduced, only the MODEL FORMULA can be "
            "evaluated on ensembles we generate ourselves. A like-for-like comparison must "
            "therefore be run on a common molecule set with a common conformer protocol, and "
            "the author's published CV numbers must not be quoted against our MAE."
        ),
    }
    (OUT / "craft_provenance.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT / 'craft_provenance.json'}")
    print(f"commit {COMMIT[:12]}, MIT, {len(files)} files")
    print(f"parameters parsed: {n_params} (author declares 41)")
    print(f"reference liquids: {len(reference)}")


if __name__ == "__main__":
    main()
