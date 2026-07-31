#!/usr/bin/env python3
"""Fail-closed validation for the neutral public download repository."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


EXPECTED_FILES = frozenset(
    {
        ".nojekyll",
        "assets/site.css",
        "assets/site.js",
        "favicon.svg",
        "index.html",
        "release.json",
    }
)
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 5 * 1024 * 1024
VERSION_PATTERN = re.compile(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\Z")
EMAIL_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)
HOME_PATH_PATTERNS = (
    re.compile(r"(?i)(?:/Users|/home)/[^/\x00\r\n\t '\"<>]+"),
    re.compile(
        r"(?i)(?:[a-z]:[\\/]+|file:[\\/]+|/mnt/[a-z]/)Users[\\/]+"
        r"[^\\/\x00\r\n\t '\"<>]+"
    ),
    re.compile(r"(?i)(?:/private)?/var/folders/[^\x00\r\n\t '\"<>]+"),
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"),
)


class PublicSiteError(ValueError):
    pass


def identity_markers() -> tuple[str, ...]:
    raw = os.environ.get("PRIVATE_IDENTITY_MARKERS", "")
    markers = tuple(
        marker.strip().casefold()
        for marker in raw.splitlines()
        if marker.strip()
    )
    if not markers:
        raise PublicSiteError(
            "PRIVATE_IDENTITY_MARKERS is required; public deployment is fail-closed"
        )
    if any(len(marker) < 3 for marker in markers):
        raise PublicSiteError("identity markers must each contain at least 3 characters")
    return markers


def read_exact_site(site_root: Path) -> dict[str, str]:
    site_root = site_root.absolute()
    if site_root.is_symlink() or not site_root.is_dir():
        raise PublicSiteError("site root is missing or is a symlink")

    entries = list(site_root.rglob("*"))
    if any(entry.is_symlink() for entry in entries):
        raise PublicSiteError("site must not contain symlinks")
    actual_files = {
        entry.relative_to(site_root).as_posix()
        for entry in entries
        if entry.is_file()
    }
    if actual_files != EXPECTED_FILES:
        raise PublicSiteError("site files differ from the reviewed allow-list")

    total_size = 0
    decoded: dict[str, str] = {}
    for relative_name in sorted(actual_files):
        data = (site_root / relative_name).read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise PublicSiteError("a public site file exceeds the size limit")
        total_size += len(data)
        if total_size > MAX_TOTAL_BYTES:
            raise PublicSiteError("public site exceeds the total size limit")
        try:
            decoded[relative_name] = data.decode("utf-8")
        except UnicodeError as exc:
            raise PublicSiteError("public site files must be UTF-8 text") from exc
    return decoded


def validate_release_metadata(text: str) -> None:
    try:
        release = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PublicSiteError("release.json is invalid") from exc
    if not isinstance(release, dict) or set(release) != {
        "base_url",
        "published_at",
        "version",
    }:
        raise PublicSiteError("release.json fields differ from the fixed schema")
    if not isinstance(release["version"], str) or VERSION_PATTERN.fullmatch(
        release["version"]
    ) is None:
        raise PublicSiteError("release version is invalid")
    if not isinstance(release["published_at"], str):
        raise PublicSiteError("release timestamp is invalid")
    try:
        published = datetime.fromisoformat(
            release["published_at"].replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise PublicSiteError("release timestamp is invalid") from exc
    if published.tzinfo is None or published.utcoffset() is None:
        raise PublicSiteError("release timestamp must include a timezone")

    if not isinstance(release["base_url"], str):
        raise PublicSiteError("release base URL is invalid")
    parsed = urlsplit(release["base_url"])
    try:
        parsed.port
    except ValueError as exc:
        raise PublicSiteError("release base URL has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/")
    ):
        raise PublicSiteError("release base URL must be a credential-free HTTPS directory")


def verify(site_root: Path) -> None:
    markers = identity_markers()
    files = read_exact_site(site_root)
    combined = "\n".join(files.values())
    folded = combined.casefold()
    if any(marker in folded for marker in markers):
        raise PublicSiteError("blocked a private identity marker; matching text was not logged")
    if EMAIL_PATTERN.search(combined) or any(
        pattern.search(combined) for pattern in HOME_PATH_PATTERNS
    ):
        raise PublicSiteError("blocked an email or personal path; matching text was not logged")
    if any(pattern.search(combined) for pattern in SECRET_PATTERNS):
        raise PublicSiteError("blocked credential material; matching text was not logged")
    validate_release_metadata(files["release.json"])


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print("usage: verify_public_site.py SITE_DIRECTORY", file=sys.stderr)
        return 2
    try:
        verify(Path(arguments[0]))
    except (OSError, PublicSiteError) as exc:
        print(f"public site verification failed: {exc}", file=sys.stderr)
        return 1
    print("public site verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
