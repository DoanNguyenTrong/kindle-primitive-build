#!/usr/bin/env python3
"""Package one architecture of a Primitive Store app: a zip, its .sha256, and the manifest inside it.

    python3 package.py --id primitive-notes --dir notes --version 0.1.0 --arch armhf \\
        --stage build/stage --license LICENSE --install INSTALL.md --out dist

The stage folder holds the files as they are installed on the Kindle, under the app's own places: `<dir>/...`,
`documents/...` and `extensions/<dir>/...`. Everything in it is listed in the manifest. `LICENSE`, `INSTALL.md` and
`hooks/` are added beside it. Refuses a file outside the allowed places, a file that is a link, and a manifest that
fails its schema.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import zipfile

from jsonschema import Draft202012Validator, FormatChecker

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(os.path.dirname(HERE), "schema", "manifest.schema.json")
RESERVED = {"documents", "extensions", "system", "fonts", "screensaver", "koreader"}
HOOKS = {"hooks/post-install.sh", "hooks/pre-uninstall.sh"}


def allowed_place(rel, dir_):
    parts = rel.split("/")
    if parts[0] == "documents":
        return len(parts) >= 2
    if parts[0] == "extensions":
        return len(parts) >= 3 and parts[1] == dir_
    return parts[0] == dir_ and dir_ not in RESERVED and len(parts) >= 2


def stage_files(stage):
    found = []
    for root, dirs, files in os.walk(stage):
        for name in files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                raise SystemExit(f"a link is not allowed in a package: {full}")
            found.append(os.path.relpath(full, stage).replace(os.sep, "/"))
    return sorted(found)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--arch", required=True, choices=["armhf", "armel"])
    ap.add_argument("--stage", required=True)
    ap.add_argument("--license", required=True)
    ap.add_argument("--install", required=True)
    ap.add_argument("--firmware-min", default="5.16.3")
    ap.add_argument("--requires", action="append", default=[], help="id=>=version, repeatable")
    ap.add_argument("--hooks", action="store_true", help="include hooks/ from the stage folder")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[0-9]+(\.[0-9]+){1,2}(-p[0-9]+)?", args.version):
        raise SystemExit("version must look like 1.2.3, 2026.10, or 2.6-p1")
    files = stage_files(args.stage)
    if not files:
        raise SystemExit("the stage folder is empty")
    for f in files:
        if f.startswith("hooks/"):
            if not args.hooks or f not in HOOKS:
                raise SystemExit(f"{f}: hooks are only allowed with --hooks, and only with the two names")
            continue
        if not allowed_place(f, args.dir):
            raise SystemExit(f"{f} is outside the places an app may use ({args.dir}/, documents/, extensions/{args.dir}/)")
    installed = [f for f in files if not f.startswith("hooks/")]
    hooks = [f for f in files if f.startswith("hooks/")]

    requires = {}
    for item in args.requires:
        name, _, rng = item.partition("=")
        if not rng.startswith(">="):
            raise SystemExit("requires must be id=>=version")
        requires[name] = rng

    manifest = {
        "schema": 1,
        "id": args.id,
        "dir": args.dir,
        "version": args.version,
        "arch": args.arch,
        "firmware": {"min": args.firmware_min, "max": None},
        "requires": requires,
        "files": installed,
        "hooks": hooks,
    }
    validator = Draft202012Validator(json.load(open(SCHEMA, encoding="utf-8")), format_checker=FormatChecker())
    errors = list(validator.iter_errors(manifest))
    if errors:
        raise SystemExit("the manifest is not valid: " + errors[0].message)

    top = f"{args.id}-{args.version}"
    name = f"{args.id}-{args.version}-{args.arch}.zip"
    os.makedirs(args.out, exist_ok=True)
    zip_path = os.path.join(args.out, name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/manifest.json", json.dumps(manifest, indent=2) + "\n")
        z.write(args.license, f"{top}/LICENSE")
        z.write(args.install, f"{top}/INSTALL.md")
        for f in installed + hooks:
            info = zipfile.ZipInfo(f"{top}/{f}")
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(os.path.join(args.stage, f), "rb") as src:
                z.writestr(info, src.read())

    digest = hashlib.sha256(open(zip_path, "rb").read()).hexdigest()
    with open(zip_path + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{digest}  {name}\n")
    print(f"packaged {zip_path}")
    print(f"sha256   {digest}")
    print(f"size     {os.path.getsize(zip_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
