# -*- coding: utf-8 -*-
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from memorylake_backend import install


def _tar_with_binary(tag: str, triple: str, body: bytes = b"#!/bin/sh\necho hi\n") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in ((f"memorylake-{tag}-{triple}/memorylake", body), (f"memorylake-{tag}-{triple}/LICENSE", b"x")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _fetcher(tag: str, triple: str, archive: bytes, sha_hex: str | None = None):
    asset = install.archive_name(tag, triple)
    sha_hex = sha_hex or hashlib.sha256(archive).hexdigest()
    urls = {
        install.LATEST_RELEASE_URL: json.dumps({"tag_name": tag}).encode(),
        install.DOWNLOAD_URL.format(tag=tag, asset=asset): archive,
        install.DOWNLOAD_URL.format(tag=tag, asset=f"{asset}.sha256"): f"{sha_hex}  {asset}\n".encode(),
    }
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return urls[url]

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


def test_target_triple_mapping() -> None:
    assert install.target_triple("Darwin", "arm64") == "aarch64-apple-darwin"
    assert install.target_triple("Linux", "x86_64") == "x86_64-unknown-linux-gnu"
    assert install.target_triple("Windows", "AMD64") == "x86_64-pc-windows-msvc"
    assert install.target_triple("FreeBSD", "x86_64") is None
    assert install.target_triple("Linux", "riscv64") is None
    assert install.archive_name("v1", "x86_64-pc-windows-msvc").endswith(".zip")
    assert install.archive_name("v1", "x86_64-apple-darwin").endswith(".tar.gz")


def test_parse_sha256_file_formats() -> None:
    assert install.parse_sha256_file("ABC  a.tar.gz\n", "a.tar.gz") == "abc"
    assert install.parse_sha256_file("abc *a.tar.gz", "a.tar.gz") == "abc"
    assert install.parse_sha256_file("f" * 64, "a.tar.gz") == "f" * 64
    with pytest.raises(install.InstallError):
        install.parse_sha256_file("abc  other.tar.gz", "a.tar.gz")


def test_good_checksum_installs_executable(tmp_path: Path) -> None:
    tag, triple = "v20260828", "aarch64-apple-darwin"
    archive = _tar_with_binary(tag, triple)
    fetch = _fetcher(tag, triple, archive)
    binary = install.install_cli(tmp_path / "bin", fetch=fetch, triple=triple)
    assert binary == tmp_path / "bin" / "memorylake"
    assert binary.read_bytes() == b"#!/bin/sh\necho hi\n"
    assert binary.stat().st_mode & 0o111
    assert fetch.calls[0] == install.LATEST_RELEASE_URL  # type: ignore[attr-defined]
    assert not [p for p in (tmp_path / "bin").iterdir() if p.name.startswith(".memorylake-")]


def test_bad_checksum_installs_nothing(tmp_path: Path) -> None:
    tag, triple = "v1", "x86_64-unknown-linux-gnu"
    archive = _tar_with_binary(tag, triple)
    fetch = _fetcher(tag, triple, archive, sha_hex="0" * 64)
    with pytest.raises(install.ChecksumMismatch):
        install.install_cli(tmp_path / "bin", fetch=fetch, tag=tag, triple=triple)
    assert not (tmp_path / "bin").exists()


def test_archive_without_binary_is_an_error(tmp_path: Path) -> None:
    tag, triple = "v1", "x86_64-apple-darwin"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("README")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    fetch = _fetcher(tag, triple, buf.getvalue())
    with pytest.raises(install.InstallError, match="does not contain"):
        install.install_cli(tmp_path / "bin", fetch=fetch, tag=tag, triple=triple)


def test_zip_archives_for_windows() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("memorylake-v1-x86_64-pc-windows-msvc/memorylake.exe", b"MZ")
    assert install.extract_binary(buf.getvalue(), "memorylake-v1-x86_64-pc-windows-msvc.zip") == b"MZ"


def test_unsupported_platform_is_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install.platform, "system", lambda: "Plan9")
    with pytest.raises(install.InstallError, match="no prebuilt"):
        install.install_cli(tmp_path, fetch=lambda url: b"")
