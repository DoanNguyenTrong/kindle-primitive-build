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
import shutil
import stat
import sys
import tempfile
import zipfile

from jsonschema import Draft202012Validator, FormatChecker

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(os.path.dirname(HERE), "schema", "manifest.schema.json")
RESERVED = {"documents", "extensions", "system", "fonts", "screensaver", "koreader"}
HOOKS = {"hooks/post-install.sh", "hooks/pre-uninstall.sh"}
MAX_PACKAGE_BYTES = 200 * 1024 * 1024
MAX_FILES = 5000


def allowed_place(rel, dir_):
    parts = rel.split("/")
    if parts[0] == "documents":
        return len(parts) >= 2
    if parts[0] == "extensions":
        return len(parts) >= 3 and parts[1] == dir_
    return parts[0] == dir_ and dir_ not in RESERVED and len(parts) >= 2


def stage_files(stage):
    if os.path.islink(stage):
        raise SystemExit("the stage folder must not be a link")
    found = []
    for root, dirs, files in os.walk(stage):
        for name in dirs + files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                raise SystemExit(f"a link is not allowed in a package: {full}")
        for name in files:
            full = os.path.join(root, name)
            if not os.path.isfile(full):
                raise SystemExit(f"only regular files are allowed in a package: {full}")
            found.append(os.path.relpath(full, stage).replace(os.sep, "/"))
    return sorted(found)


def write_file(archive, name, source, executable=False):
    info = zipfile.ZipInfo(name)
    info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with open(source, "rb") as src, archive.open(info, "w") as dest:
        shutil.copyfileobj(src, dest)


def scan(files, manifest_json):
    try:
        patterns = [
            re.compile(pattern.encode())
            for pattern in os.environ.get("PACKAGE_SCAN_PATTERNS", "").splitlines()
            if pattern
        ]
    except re.error:
        raise SystemExit("an invalid secret scan expression was configured") from None
    for pattern in patterns:
        if pattern.search(manifest_json):
            raise SystemExit("a configured secret scan expression matched a package entry")
    if patterns:
        for name, source, _ in files:
            with open(source, "rb") as data:
                contents = data.read(MAX_PACKAGE_BYTES + 1)
            if any(pattern.search(contents) or pattern.search(name.encode()) for pattern in patterns):
                raise SystemExit("a configured secret scan expression matched a package entry")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--arch", required=True, choices=["armhf", "armel"])
    ap.add_argument("--stage", required=True)
    ap.add_argument("--license", required=True)
    ap.add_argument("--docs-license")
    ap.add_argument("--install", required=True)
    ap.add_argument("--firmware-min", default="5.16.3")
    ap.add_argument("--requires", action="append", default=[], help="id=>=version, repeatable")
    ap.add_argument("--hooks", action="store_true", help="include hooks/ from the stage folder")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", args.dir) or args.dir in RESERVED:
        raise SystemExit("dir must be an unreserved app folder")
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)+", args.firmware_min):
        raise SystemExit("the minimum firmware must be a dotted version")
    files = stage_files(args.stage)
    if not files:
        raise SystemExit("the stage folder is empty")
    for f in files:
        if "\\" in f or any(p in ("", ".", "..") for p in f.split("/")):
            raise SystemExit(f"unsafe package filename: {f}")
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
        if (not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", name)
                or not re.fullmatch(r">=[0-9]+\.[0-9]+\.[0-9]+", rng)
                or name == args.id or name in requires):
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
    with open(SCHEMA, encoding="utf-8") as schema:
        validator = Draft202012Validator(json.load(schema), format_checker=FormatChecker())
    errors = list(validator.iter_errors(manifest))
    if errors:
        raise SystemExit("the manifest is not valid: " + errors[0].message)

    top = f"{args.id}-{args.version}"
    name = f"{args.id}-{args.version}-{args.arch}.zip"
    metadata = [("LICENSE", args.license, False), ("INSTALL.md", args.install, False)]
    if args.docs_license:
        metadata.append(("LICENSE-DOCS", args.docs_license, False))
    for f in installed + hooks:
        source = os.path.join(args.stage, f)
        executable = (
            os.stat(source).st_mode & 0o111
            or f.endswith(".sh")
            or "/bin/" in f
            or os.path.basename(f) in ("kb-kindle", "kl-launcher")
        )
        metadata.append((f, source, bool(executable)))
    manifest_json = (json.dumps(manifest, indent=2) + "\n").encode()
    if len(metadata) + 1 > MAX_FILES:
        raise SystemExit(f"the package has more than {MAX_FILES} entries")
    if len(manifest_json) + sum(os.path.getsize(source) for _, source, _ in metadata) > MAX_PACKAGE_BYTES:
        raise SystemExit(f"the package is larger than {MAX_PACKAGE_BYTES} bytes before compression")
    scan(metadata, manifest_json)

    os.makedirs(args.out, exist_ok=True)
    zip_path = os.path.join(args.out, name)
    with tempfile.TemporaryDirectory(dir=args.out) as temp:
        packed = os.path.join(temp, name)
        checksum = packed + ".sha256"
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
            info = zipfile.ZipInfo(f"{top}/manifest.json")
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, manifest_json)
            for f, source, executable in metadata:
                write_file(archive, f"{top}/{f}", source, executable)
        hasher = hashlib.sha256()
        with open(packed, "rb") as f:
            for chunk in iter(lambda: f.read(64 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        with open(checksum, "w", encoding="utf-8") as f:
            f.write(f"{digest}  {name}\n")
        os.replace(packed, zip_path)
        os.replace(checksum, zip_path + ".sha256")
    print(f"packaged {zip_path}")
    print(f"sha256   {digest}")
    print(f"size     {os.path.getsize(zip_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
