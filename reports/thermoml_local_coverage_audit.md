# Tier-0 independent coverage audit of the local ThermoML dielectric corpus

**Date:** 2026-09-24
**Probe:** probes/thermoml_local_coverage_probe.py
**Summary:** probes/thermoml_local_coverage_summary.json
**Status:** closed. No new values; the audit exists to stop a silent extraction
gap from masquerading as "no data".

## Why this audit exists

The G1+ source-priority pass concluded that propylene carbonate, ethylene
carbonate, vinylene carbonate, fluoroethylene carbonate and
methoxypropionitrile have no local ThermoML dielectric observation. That
conclusion is load-bearing: it is the stated reason for reaching into external
compilations for those five molecules.

A claim of absence is only as good as the search behind it. A plausible failure
mode is that the compounds *are* in the local corpus and the extraction dropped
them. This probe re-derives the absence from the raw XML text rather than from
the extraction output, so the two can be compared.

## Method

For each target the probe reports three independent counts:

| Count | What it means |
| --- | --- |
| xml_files_mentioning_inchikey | raw text grep of every local ThermoML XML for the standard InChIKey. Fires even if the compound is only a mixture component. |
| xml_files_with_permittivity_text | of those, how many contain any permittivity or dielectric wording at all |
| extracted_pure_observations | rows in the parsed extraction attributed to that InChIKey |

A target is only "locally supported" when the third count is non-zero.

## Result

242 XML files and 11,646 extracted observations were scanned.

| Target | XML mentions | with permittivity text | pure extracted | Verdict |
| --- | ---: | ---: | ---: | --- |
| propylene carbonate | 26 | 0 | 0 | mentioned only in non-dielectric studies |
| ethylene carbonate | 11 | 0 | 0 | mentioned only in non-dielectric studies |
| vinylene carbonate | 0 | 0 | 0 | absent from local corpus |
| fluoroethylene carbonate | 0 | 0 | 0 | absent from local corpus |
| 3-methoxypropionitrile | 1 | 0 | 0 | mentioned only in non-dielectric studies |
| diglyme | 2 | 2 | 9 | locally supported |
| triglyme | 3 | 3 | 15 | locally supported |
| tetraglyme | 4 | 4 | 11 | locally supported |
| adiponitrile | 1 | 1 | 31 | locally supported |
| glutaronitrile | 1 | 1 | 31 | locally supported |

## What changed relative to the earlier claim

The earlier Tier-0 note said simply that PC and EC "were not found" in the local
corpus. That wording was too weak and, read literally, wrong: propylene
carbonate is named in **26** local XML files and ethylene carbonate in **11**.
The accurate statement is narrower and stronger:

> PC and EC appear in the local corpus only as mixture components of
> non-dielectric studies. Not one of the 26 PC files and not one of the 11 EC
> files contains any permittivity or dielectric wording, and the parsed
> extraction holds zero rows for either InChIKey. The "no local dielectric data"
> claim is therefore reproduced independently rather than inherited from the
> extraction.

This matters because it distinguishes two very different situations. If the
compounds were simply never in the cache, a broader crawl might find them. If
they are present in dozens of files that never measured permittivity, then the
cache is not the problem and re-crawling the same corpus cannot help. The second
is what the data shows.

## The other half of the picture

The same audit confirms the complement, which is what makes the "upgrade" side
of G1+ credible: the three glymes and the two dinitriles already carry
pure-component local observations. Those upgrades need no new crawl at all; they
were sitting in the cache.

Note the adiponitrile InChIKey. An earlier ad-hoc grep used
BTGRAWLCACVEDO-UHFFFAOYSA-N and found nothing, which would have looked like a
second absence. The correct key is BTGRAWJCKBQKAO-UHFFFAOYSA-N and it matches 31
pure observations. The probe pins the corrected key so the mistake cannot recur.

## Limitation

The permittivity wording scan is deliberately over-inclusive: it fires on
abstract text, so a non-zero count does not by itself prove a structured
dielectric dataset exists. A zero count, however, is decisive. The corpus is the
locally cached ThermoML subset (dielectric and permittivity queries), not the
complete 2020 ThermoML archive, so absence here is absence from this cache only.

## Verification

tests/test_thermoml_local_coverage_probe.py passes 6 tests, including a
regression test pinning the full target split: five locally supported, five
without local dielectric data, with PC at 26 mentions and 0 permittivity files.
Ruff is clean.
