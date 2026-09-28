"""Pack / restore the raw INGRES API snapshot (published as a GitHub Release asset).

    python scripts/snapshot_raw.py pack      # -> dist/ingres_raw_<date>.tar + .sha256 + manifest
    python scripts/snapshot_raw.py restore dist/ingres_raw_<date>.tar

Raw files are already gzipped, so a plain tar is used. The manifest lists every file with
its sha256 so a restored snapshot can be verified file-by-file.
"""
import hashlib
import json
import sys
import tarfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/ingres_api"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pack() -> Path:
    files = sorted(RAW.glob("*/*.json.gz"))
    manifest = {"source": "https://ingres.iith.ac.in/api/gec/getBusinessDataForUserOpen",
                "created": date.today().isoformat(),
                "years": {y.name: len(list(y.glob("*.json.gz"))) for y in sorted(RAW.iterdir()) if y.is_dir()},
                "files": {str(f.relative_to(RAW)).replace("\\", "/"): sha256(f) for f in files}}
    out = ROOT / "dist" / f"ingres_raw_{manifest['created']}.tar"
    out.parent.mkdir(exist_ok=True)
    mpath = RAW / "MANIFEST.json"
    mpath.write_text(json.dumps(manifest, indent=1))
    with tarfile.open(out, "w") as tar:
        tar.add(mpath, arcname="ingres_api/MANIFEST.json")
        for f in files:
            tar.add(f, arcname=f"ingres_api/{f.relative_to(RAW).as_posix()}")
    out.with_suffix(".tar.sha256").write_text(f"{sha256(out)}  {out.name}\n")
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB, {len(files)} files)")
    return out


def restore(archive: Path) -> None:
    with tarfile.open(archive) as tar:
        tar.extractall(RAW.parent, filter="data")
    manifest = json.loads((RAW / "MANIFEST.json").read_text())
    bad = [k for k, h in manifest["files"].items() if sha256(RAW / k) != h]
    if bad:
        raise SystemExit(f"{len(bad)} files failed checksum, e.g. {bad[:3]}")
    print(f"restored and verified {len(manifest['files'])} files into {RAW}")


if __name__ == "__main__":
    {"pack": lambda: pack(), "restore": lambda: restore(Path(sys.argv[2]))}[sys.argv[1]]()
