"""Read-only WHU audit: distinguish geometry limits, interrupted and unstarted jobs."""

from __future__ import annotations

import argparse
import csv
import json
import shlex
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from rdkit import Chem

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "outputs/b740_expansion/dft_expansion"
OUT = ROOT / "outputs/b750_completion/failure_diagnostics"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True)
    parser.add_argument("--known-hosts", required=True)
    args = parser.parse_args()
    import paramiko

    jobs = json.loads((BASE / "package_opt/manifest.json").read_text())["jobs"]
    latest = list(
        csv.DictReader(
            (BASE / "results_opt/validation/validation_ledger.csv").open(encoding="utf-8")
        )
    )
    statuses = {r["inchikey"]: r for r in latest}
    restart = json.loads((ROOT / "outputs/b750_completion/retry_opt/manifest.json").read_text())[
        "jobs"
    ]
    restarted = {r["inchikey"] for r in restart}
    client = paramiko.SSHClient()
    client.load_host_keys(args.known_hosts)
    client.connect("202.114.96.180", username="pengqihang", key_filename=args.key, timeout=20)
    remote_code = """import json,pathlib,re,hashlib
jobs=json.loads(JOBS_JSON)
rows=[]
for i,job in enumerate(jobs,1):
 ik=job['inchikey']; folder=pathlib.Path('/project/pengqihang/b742/package_opt/jobs')/ik; p=folder/'job.out'
 r={'inchikey':ik,'array_task':(i-1)//8+1,'output_exists':p.is_file(),'restart_xyz_exists':(folder/'job.xyz').is_file()}
 if p.is_file():
  raw=p.read_bytes(); text=raw.decode('utf-8',errors='replace'); lines=text.splitlines()
  cycles=re.findall(r'GEOMETRY OPTIMIZATION CYCLE\\s+(\\d+)',text,re.I)
  evidence=[{'line':k+1,'text':line.strip()} for k,line in enumerate(lines) if re.search(r'maximum number|did not converge|optimization.*converg|optimization.*fail|SCF.*NOT.*CONVERG|aborting|error termination|TOTAL RUN TIME',line,re.I)]
  r.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),normal='ORCA TERMINATED NORMALLY' in text,optimization_converged='THE OPTIMIZATION HAS CONVERGED' in text,last_geometry_cycle=int(cycles[-1]) if cycles else None,evidence=evidence[-20:],tail='\\n'.join(lines[-18:]))
 rows.append(r)
print(json.dumps(rows))
""".replace("JOBS_JSON", repr(json.dumps(jobs)))
    try:
        _, out, err = client.exec_command("python3 -c " + shlex.quote(remote_code), timeout=90)
        payload = out.read().decode()
        error = err.read().decode()
        if out.channel.recv_exit_status() != 0:
            raise RuntimeError(error)
        remote = json.loads(payload)
        _, out, err = client.exec_command(
            "sacct -j 4592091,4592244,4625122 --format=JobID,State,Elapsed,ExitCode -n", timeout=30
        )
        accounting = out.read().decode()
        _, out, err = client.exec_command("squeue -u pengqihang", timeout=30)
        queue = out.read().decode()
    finally:
        client.close()
    strata = defaultdict(Counter)
    for row, job in zip(remote, jobs, strict=True):
        ik = row["inchikey"]
        status = statuses[ik]["status"]
        mol = Chem.MolFromSmiles(job["smiles"])
        ionic = len(Chem.GetMolFrags(mol)) > 1
        row.update(
            name=job["name"],
            n_atoms=job["n_atoms"],
            is_multifragment=ionic,
            latest_status=status,
            retried=ik in restarted,
        )
        if status == "ACCEPTED":
            diagnosis = "ACCEPTED_AFTER_RETRY" if ik in restarted else "ACCEPTED_ORIGINAL"
        elif not row["output_exists"]:
            diagnosis = "NOT_STARTED_NO_OUTPUT"
        elif not row.get("normal"):
            diagnosis = "INTERRUPTED_OUTPUT"
        elif not row.get("optimization_converged"):
            diagnosis = "GEOMETRY_NOT_CONVERGED_NORMAL_EXIT"
        else:
            diagnosis = "OTHER_PROPERTY_FAILURE"
        row["diagnosis"] = diagnosis
        strata["multifragment" if ionic else "single_fragment"][status] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": "b750.failure_diagnostics/v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "counts": dict(Counter(r["diagnosis"] for r in remote)),
        "chemistry_strata": {k: dict(v) for k, v in strata.items()},
        "sacct": accounting,
        "queue": queue,
        "rows": remote,
        "guard": "Multifragment is a structural grouping; observational association is not proof of a causal chemistry failure.",
    }
    (OUT / "failure_diagnostics.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in doc.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
