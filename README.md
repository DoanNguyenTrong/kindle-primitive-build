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
- The binary crate's Cargo version, equal to the tag without `v`.

The workflow accepts `arches` as a comma-separated list, `armhf` by default, and `firmware-min` as a dotted version.
`armel` targets ARM soft-float and requires an app stage script that handles it. `licence-file`, `docs-licence-file`,
`install-file` and `changelog-file` customize document paths. Set `legacy-usb: true` for an app that also provides
`scripts/package-release.sh` and wants to publish its existing USB archive alongside the Store package.

Native app projects that use the sibling `doannt-kindle-tools` workspace pass its approved revision as
`sibling-tools-ref`. The workflow checks out that revision and exposes it as a sibling, using the same paths as on a
developer's computer.

To scan archives in CI, pass the caller's `PACKAGE_SCAN_PATTERNS` secret as `package-scan-patterns`. Each nonempty line is
a regular expression applied to staged names, contents and the manifest. The packager reports only that a match occurred.
For a local scan set the `PACKAGE_SCAN_PATTERNS` environment variable before running the packager.

## Check it locally

```sh
python3 scripts/package.py --id primitive-notes --dir notes --version 0.1.0 --arch armhf \
  --stage build/stage --license LICENSE --install INSTALL.md --out dist
```

The launcher's `kl-store` crate reads these packages in its tests (`KL_TEST_PACKAGE=dist/<zip> cargo test -p kl-store`).

Release workflows should pin an approved workflow revision. The reusable workflow checks out its packager at that same revision.
