# v1.2.1 release notes

**Released:** 2026-09-28 · **Dataset:** v0.3.3, `data/dielectric_v03.csv` **unchanged**
(digest `ff2142936e06e04b329b70f8597574f75349e54ce876e9fff81309e6d35ccce4`) · **Archived by:** Zenodo
**DOI:** https://doi.org/10.5281/zenodo.23006276 (concept DOI
https://doi.org/10.5281/zenodo.22957695), minted from this GitHub release.

This is a **patch release**. It adds no lane, no model and no reading. It exists because the
`v1.2` archive was self-contradictory, and the only way to correct an archive is to archive the
corrected tree.

## Why it exists

The `v1.2` tag sits on `e57de46`, and the tree at that commit predates three corrections:

- `README.md` there read `DOI (v1.2): pending (Zenodo mints it from this GitHub release;
  backfilled in the next commit)` — a placeholder for the very DOI the archive was being given;
- `README.md` there read `DOI (v1.1): https://doi.org/10.5281/zenodo.23001299`, a duplicate
  deposit that was later deleted and now resolves to **HTTP 410 Gone**;
- `paper/release_notes_v1.2.md` there carried the same `pending` line.

So the archived zip carried a dead link and its own DOI placeholder. Three commits
(`15d4db5`, `81c761d`, `102198d`) fixed the tree, but a tag does not move: only a new release
archives a corrected tree.

## What the tag points at

`v1.2.1` points at `102198db7cc12556778bde17f423aea9ca55ae09`, where every DOI line in
`README.md` resolves:

- `DOI (v1.2): https://doi.org/10.5281/zenodo.23001632` — live;
- `DOI (v1.1): https://doi.org/10.5281/zenodo.23001408` — live (the only v1.1 record left once
  the two duplicate deposits were removed);
- `DOI (v1.0): https://doi.org/10.5281/zenodo.22957696` — live;
- `Concept DOI: https://doi.org/10.5281/zenodo.22957695` — live.

## Discipline this release keeps

- No tag is moved and no GitHub release body is edited. Release-body edits have already been
  measured under this concept to re-trigger archiving, so the correction ships as a new release.
- `v1.2` and its record `10.5281/zenodo.23001632` are **kept**. One version number keeps exactly
  one record; `v1.2` and `v1.2.1` are two version numbers.
- Frozen readings are untouched: baseline `0.4091179943351143`, headline `0.4766400383507876`,
  honest epsilon endpoint `0.5861142332208197`. No lane is promoted and no main-scoreboard
  attempt is added (cumulative 11).
- Dataset bytes are unchanged; no Reaxys value and no restricted-library value is in the archive.

## Root cause, and the Week 20 fix

The root cause is not a mistyped DOI. `README.md` and `release_notes_*.md` each carry a line that
describes *their own* version DOI, and a version DOI cannot exist before the tag is frozen — so
every archive necessarily carries either a placeholder or a stale DOI. Week 20 points the
archived files at the concept DOI for the current version, and keeps version-specific DOIs in the
GitHub release body and the backfill commit, neither of which Zenodo archives.

## Reproduce

```
python probes/export_week19_results.py --overwrite
python -m pytest -q
```
