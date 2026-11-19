# Primitive Store build

The shared release pipeline for Primitive Store apps: one reusable GitHub workflow and the packager it calls.

- `.github/workflows/package.yml`: on a `v*` tag of an app, tests the app, builds it for each architecture, stages the
  installed files, packages them, and publishes the release with the zips and their `.sha256` files.
- `scripts/package.py`: builds `<id>-<version>-<arch>.zip` with a `manifest.json` (the exact file list), a `LICENSE`,
  an `INSTALL.md` and the optional hooks, and writes its `.sha256`. It refuses files outside the app's places, links,
  and manifests that fail the schema (`schema/manifest.schema.json`).

## What an app provides

- `scripts/stage.sh <arch>`: copies the installed files into `build/stage/`, under `<dir>/`, `documents/` and
  `extensions/<dir>/`. Nothing else goes in the stage.
- `LICENSE` and `INSTALL.md` at the top of the repository.
- `CHANGELOG.md`, used as the release notes.
- `Cargo.toml`'s version, equal to the tag without `v`.

## Check it locally

```sh
python3 scripts/package.py --id primitive-notes --dir notes --version 0.1.0 --arch armhf \
  --stage build/stage --license LICENSE --install INSTALL.md --out dist
```

The launcher's `kl-store` crate reads these packages in its tests (`KL_TEST_PACKAGE=dist/<zip> cargo test -p kl-store`).

## Status

The packager is tested on the Mac (the layout, the refusals, and the store's reading of its output). The workflow has
not run on GitHub yet: it needs the repository created and a first app to call it.
