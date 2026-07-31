#!/usr/bin/env python3
"""Download the CSS build toolchain into ``tools/``.

Body Shop compiles its stylesheet with Tailwind, but deliberately has **no npm
dependency**: the Tailwind CLI ships as a self-contained binary and daisyUI is a
plain npm tarball of CSS and a plugin entry point, so both can be fetched
without Node installed. That keeps the one-command setup story intact for a
Python project and matches the roadmap's "Tailwind CLI only" constraint.

Everything this writes is gitignored. The *compiled* stylesheet
(``app/static/css/styles.css``) is committed instead, so running the app — in
development, in CI, or on a server — never needs this script. Only editing
``app/static/css/input.css`` does.

Usage::

    python tools/fetch_css_toolchain.py
"""

from __future__ import annotations

import io
import platform
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

#: Pinned so a rebuild on another machine produces a byte-identical stylesheet.
TAILWIND_VERSION = "4.3.3"
DAISYUI_VERSION = "5.7.7"

TOOLS = Path(__file__).resolve().parent

#: ``platform.system()``/``machine()`` pair -> Tailwind release asset suffix.
TAILWIND_ASSETS = {
    ("Windows", "AMD64"): "windows-x64.exe",
    ("Windows", "ARM64"): "windows-arm64.exe",
    ("Darwin", "arm64"): "macos-arm64",
    ("Darwin", "x86_64"): "macos-x64",
    ("Linux", "x86_64"): "linux-x64",
    ("Linux", "aarch64"): "linux-arm64",
}


def tailwind_binary_name() -> str:
    """Return the local filename for the Tailwind CLI on this platform."""
    return "tailwindcss.exe" if platform.system() == "Windows" else "tailwindcss"


def download(url: str, label: str) -> bytes:
    """Fetch ``url``, reporting progress under ``label``.

    Output stays ASCII-only: Windows consoles default to cp1252, which raises
    ``UnicodeEncodeError`` on characters as ordinary as an arrow.
    """
    print(f"  {label} <- {url}")
    with urllib.request.urlopen(url) as response:  # noqa: S310 - pinned https URLs
        return response.read()


def fetch_tailwind() -> None:
    """Download the standalone Tailwind CLI for the current platform."""
    key = (platform.system(), platform.machine())
    asset = TAILWIND_ASSETS.get(key)
    if asset is None:
        supported = ", ".join(f"{s}/{m}" for s, m in TAILWIND_ASSETS)
        sys.exit(f"No Tailwind CLI build for {key[0]}/{key[1]}. Supported: {supported}")

    target = TOOLS / tailwind_binary_name()
    url = (
        "https://github.com/tailwindlabs/tailwindcss/releases/download/"
        f"v{TAILWIND_VERSION}/tailwindcss-{asset}"
    )
    target.write_bytes(download(url, f"tailwindcss {TAILWIND_VERSION}"))
    target.chmod(0o755)
    print(f"  -> {target.relative_to(TOOLS.parent)} ({target.stat().st_size:,} bytes)")


def fetch_daisyui() -> None:
    """Unpack the daisyUI npm tarball into ``tools/daisyui``.

    ``input.css`` loads it with ``@plugin "../../../tools/daisyui"``, so the
    package only has to exist on disk — npm never runs.
    """
    url = (
        "https://registry.npmjs.org/daisyui/-/"
        f"daisyui-{DAISYUI_VERSION}.tgz"
    )
    payload = download(url, f"daisyui {DAISYUI_VERSION}")

    target = TOOLS / "daisyui"
    if target.exists():
        shutil.rmtree(target)

    # PEP 706's extraction filter shipped in 3.12 and was backported to 3.11.4,
    # 3.10.12, 3.9.17 and 3.8.17 — so the interpreter version alone does not
    # tell you whether ``extract()`` accepts ``filter=``; on an older patch
    # release passing it is a TypeError. ``tarfile.data_filter`` landed with the
    # keyword, so probe for that instead of comparing version tuples.
    #
    # Where it is missing the extraction is unfiltered, which is how a malicious
    # tarball would write outside ``target``. That is narrow here — a pinned
    # package over HTTPS from the npm registry — but it is a trust decision, so
    # say so rather than degrading in silence.
    filtered = hasattr(tarfile, "data_filter")
    extract_kwargs = {"filter": "data"} if filtered else {}
    if not filtered:
        print(
            "  !  this Python predates PEP 706, so the tarball is extracted "
            "unfiltered; upgrade to 3.10.12+ / 3.11.4+ to restore it"
        )

    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        for member in archive.getmembers():
            # npm tarballs nest everything under "package/"; flatten that away.
            if not member.name.startswith("package/"):
                continue
            member.name = member.name[len("package/") :]
            if member.name:
                archive.extract(member, target, **extract_kwargs)

    print(f"  -> {target.relative_to(TOOLS.parent)}/")


def main() -> None:
    print("Fetching the Body Shop CSS toolchain (no npm required):")
    fetch_tailwind()
    fetch_daisyui()
    print(
        "\nDone. Build the stylesheet with:\n"
        f"  tools/{tailwind_binary_name()} "
        "-i app/static/css/input.css -o app/static/css/styles.css --minify"
    )


if __name__ == "__main__":
    main()
