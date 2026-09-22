"""Download the pinned SciFact release and check file hashes.

Fetches ``PIN.json`` ``source.url``, checks ``tarball_sha256``, and extracts
``claims_train.jsonl``, ``claims_dev.jsonl``, ``claims_test.jsonl``, and
``corpus.jsonl`` into ``data/raw/scifact/``. Raw files stay gitignored.

Usage (from the repository root):

    python3 -m data.pins.scifact.download_verify
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import urllib.request
from pathlib import Path

PIN_RELATIVE = Path("data/pins/scifact/PIN.json")
TARBALL_NAME = "data.tar.gz"


class PinMismatch(RuntimeError):
    """Raised when a downloaded or extracted file does not match PIN.json."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_pin(root: Path) -> dict:
    path = root / PIN_RELATIVE
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_jsonl_records(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _pinned_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    raw_root = (root / "data" / "raw").resolve()
    if not path.is_relative_to(raw_root):
        raise PinMismatch(f"PIN path is outside data/raw: {relative}")
    return path


def raw_matches_pin(root: Path, pin: dict | None = None) -> bool:
    """Return True when every pinned JSONL file exists and matches sha256 and count."""
    pin = load_pin(root) if pin is None else pin
    for meta in pin["files"].values():
        path = root / meta["path"]
        if not path.is_file():
            return False
        if file_sha256(path) != meta["sha256"]:
            return False
        if count_jsonl_records(path) != meta["n_records"]:
            return False
    return True


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "mavs-scifact-pin/1"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _extract_pinned_files(root: Path, pin: dict, tarball: Path) -> None:
    expected_names = set(pin["files"])
    with tarfile.open(tarball, "r:gz") as archive:
        chosen: dict[str, tarfile.TarInfo] = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.name.startswith("._") or "/._" in member.name:
                continue
            if "cross_validation" in member.name:
                continue
            name = Path(member.name).name
            if name in expected_names and member.name == f"data/{name}":
                chosen[name] = member
        missing = expected_names - set(chosen)
        if missing:
            raise PinMismatch(f"tarball is missing pinned files: {sorted(missing)}")
        for name, member in chosen.items():
            dest = _pinned_path(root, pin["files"][name]["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise PinMismatch(f"could not read {member.name} from the tarball")
            with extracted, dest.open("wb") as handle:
                while True:
                    chunk = extracted.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)


def ensure_scifact_raw(root: Path | None = None) -> dict[str, str]:
    """Download and extract when raw files are missing or fail the pin. Return file sha256s."""
    root = repo_root() if root is None else root
    pin = load_pin(root)
    expected_tarball = pin["source"]["tarball_sha256"]
    if raw_matches_pin(root, pin):
        return {name: meta["sha256"] for name, meta in pin["files"].items()}

    raw_dir = root / "data" / "raw" / "scifact"
    raw_dir.mkdir(parents=True, exist_ok=True)
    tarball = raw_dir / TARBALL_NAME
    url = pin["source"]["url"]
    if not tarball.is_file() or file_sha256(tarball) != expected_tarball:
        print(f"downloading {url}")
        _download(url, tarball)
    actual_tarball = file_sha256(tarball)
    if actual_tarball != expected_tarball:
        tarball.unlink(missing_ok=True)
        raise PinMismatch(
            f"tarball sha256 mismatch: {actual_tarball} != {expected_tarball}"
        )
    print(f"tarball_sha256={actual_tarball}")
    _extract_pinned_files(root, pin, tarball)
    if not raw_matches_pin(root, pin):
        raise PinMismatch("extracted SciFact files do not match PIN.json")
    for name, meta in pin["files"].items():
        print(f"verified {name} sha256={meta['sha256']} n={meta['n_records']}")
    return {name: meta["sha256"] for name, meta in pin["files"].items()}


def main() -> None:
    hashes = ensure_scifact_raw(repo_root())
    for name, digest in hashes.items():
        print(f"{name} {digest}")


if __name__ == "__main__":
    main()
