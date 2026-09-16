# -*- coding: utf-8 -*-
"""Downloading the ``memorylake`` CLI when the host has none.

QwenPaw is a long-running server, often in a container, so unlike the
terminal harnesses this plugin cannot ask the user to install the CLI first.
It fetches the release archive for the current platform, verifies the
published SHA-256 **before** anything is written, and installs the binary
``0755`` under the plugin's own state directory.

The checksum check is not optional. A mismatch raises and nothing is
installed.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import Request, urlopen

REPO = "memorylake-ai/memorylake-cli"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/download/{{tag}}/{{asset}}"
USER_AGENT = "memory-memorylake-qwenpaw-plugin"

Fetcher = Callable[[str], bytes]


class InstallError(RuntimeError):
    """The CLI could not be installed; the message is safe to show."""


class ChecksumMismatch(InstallError):
    """The download did not match its published checksum."""


def target_triple(
    system: str | None = None,
    machine: str | None = None,
) -> str | None:
    """Map the running platform to a release target, or ``None``."""
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = {
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "x86_64": "x86_64",
        "amd64": "x86_64",
    }.get(machine)
    if arch is None:
        return None
    if system == "darwin":
        return f"{arch}-apple-darwin"
    if system == "linux":
        return f"{arch}-unknown-linux-gnu"
    if system == "windows":
        return f"{arch}-pc-windows-msvc"
    return None


def archive_name(tag: str, triple: str) -> str:
    ext = "zip" if triple.endswith("windows-msvc") else "tar.gz"
    return f"memorylake-{tag}-{triple}.{ext}"


def default_fetch(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as resp:
        return resp.read()


def latest_tag(fetch: Fetcher = default_fetch) -> str:
    payload = json.loads(fetch(LATEST_RELEASE_URL).decode("utf-8"))
    tag = payload.get("tag_name") if isinstance(payload, dict) else None
    if not isinstance(tag, str) or not tag:
        raise InstallError("could not determine the latest memorylake CLI release")
    return tag


def parse_sha256_file(text: str, expected_asset: str) -> str:
    """Read ``<hex>  <filename>`` and return the hex for ``expected_asset``."""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lstrip("*") == expected_asset:
            return parts[0].lower()
        if len(parts) == 1 and len(parts[0]) == 64:
            return parts[0].lower()
    raise InstallError(f"no checksum published for {expected_asset}")


def verify_checksum(data: bytes, expected_hex: str, asset: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_hex.lower():
        raise ChecksumMismatch(
            f"checksum mismatch for {asset}: expected {expected_hex}, got {actual}",
        )


def extract_binary(data: bytes, asset: str) -> bytes:
    """Pull the ``memorylake`` executable out of a verified archive."""
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if Path(name).name in ("memorylake", "memorylake.exe"):
                    return zf.read(name)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            for member in tf.getmembers():
                if member.isfile() and Path(member.name).name == "memorylake":
                    extracted = tf.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
    raise InstallError(f"{asset} does not contain a memorylake binary")


def install_cli(
    dest_dir: Path,
    *,
    fetch: Fetcher = default_fetch,
    tag: str | None = None,
    triple: str | None = None,
) -> Path:
    """Download, verify, and install the CLI. Returns the binary path.

    Raises :class:`InstallError` (or its subclass :class:`ChecksumMismatch`)
    and leaves nothing behind on any failure.
    """
    triple = triple or target_triple()
    if triple is None:
        raise InstallError(
            f"no prebuilt memorylake CLI for {platform.system()} {platform.machine()}",
        )
    tag = tag or latest_tag(fetch)
    asset = archive_name(tag, triple)
    archive = fetch(DOWNLOAD_URL.format(tag=tag, asset=asset))
    sha_text = fetch(DOWNLOAD_URL.format(tag=tag, asset=f"{asset}.sha256")).decode("utf-8")
    verify_checksum(archive, parse_sha256_file(sha_text, asset), asset)
    binary = extract_binary(archive, asset)

    dest_dir.mkdir(parents=True, exist_ok=True)
    name = "memorylake.exe" if asset.endswith(".zip") else "memorylake"
    final = dest_dir / name
    fd, tmp_path = tempfile.mkstemp(prefix=".memorylake-", dir=dest_dir)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(binary)
        os.chmod(tmp_path, 0o755)
        os.replace(tmp_path, final)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return final
