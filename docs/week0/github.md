# GitHub Publication Checklist

The local repository is initialized on `main`. Creating or pushing a remote
repository requires a GitHub account and an authenticated `gh` CLI session;
those credentials are intentionally not inferred by this project.

## First publication

Run from the repository root:

```powershell
gh auth status
gh repo create electrolyte-solvent-dielectric-ml --public --source . --remote origin
git push -u origin main
```

If the repository should be private, replace `--public` with `--private`.

## Recommended repository settings

- Keep the default branch as `main`.
- Require the `Week 0 checks` GitHub Actions job before merging.
- Enable Issues for literature tasks and data-source verification.
- Add a `data` topic only when the first normalized batch is published.
- Do not commit publisher PDFs or raw ThermoML archives; record stable source
  URLs and checksums instead.

## First commit

The bootstrap commit created during Week 0 is titled
`chore: bootstrap week 0 repository`. Later agent deliverables should be
reviewed and committed separately from raw data.

