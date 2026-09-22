# %% [markdown]
# # P1: ThermoML Dielectric Data Probe
#
# Inspect the provisional live NIST API fallback census produced by
# `probes/p1_thermoml_dielectric.py`. The complete 2020 archive was unavailable,
# so the handbook gate was not formally executed. The gate uses the 100 unique
# pure-component zero-frequency compounds near 298 K; mixture partners remain
# in the separate all-component census.

# %%
import json
from pathlib import Path

import pandas as pd
from IPython.display import Image, display

repository_root = Path.cwd()
while not (repository_root / "pyproject.toml").is_file():
    repository_root = repository_root.parent
summary_path = repository_root / "probes" / "p1_summary.json"
observations_path = repository_root / "data" / "processed" / "dielectric_raw.csv"

summary = json.loads(summary_path.read_text(encoding="utf-8"))
observations = pd.read_csv(observations_path)

print(json.dumps(summary, ensure_ascii=False, indent=2))
print("\nRows:", len(observations))
print("Columns:", ", ".join(observations.columns))

# %%
observations.groupby("property_family").agg(
    observations=("value", "size"),
    compounds=("primary_inchi_key", "nunique"),
    median_value=("value", "median"),
)

# %%
artifacts = [Path(path) for path in summary["outputs"].values() if path.endswith(".png")]
for path in artifacts:
    print(path.name)
    display(Image(filename=str(path)))
