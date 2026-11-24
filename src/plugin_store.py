"""Client for the hosted plugin catalog
Reads the catalog from the public plugins repo's dist branch over https and holds no tokens or secrets
download verifies a zip but never installs it so it is safe to call off the main thread"""
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List

import plugin_manager

# Public repo: the Action publishes index.json and zips/ on the dist branch and GitHub serves them raw
# Replace YOUR_GITHUB_USER and YOUR_PLUGINS_REPO with your own
# SHORTCUTS_CATALOG_URL is for testing against a local server
CATALOG_BASE_URL = os.environ.get(
    "SHORTCUTS_CATALOG_URL",
    "https://raw.githubusercontent.com/Hogjects/Shortcuts/dist",
).rstrip("/")

_TIMEOUT_SECONDS = 15
_MAX_INDEX_BYTES = 1024 * 1024
_MAX_ZIP_BYTES = 10 * 1024 * 1024  # keep in step with tools/build_catalog.py in the plugins repo
_SUPPORTED_SCHEMA = 1

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_FILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}-[0-9A-Za-z][0-9A-Za-z._-]{0,31}\.zip$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StoreError(Exception):
    """Anything wrong reaching or reading the catalog
    the message is shown to the user as is"""


@dataclass
class CatalogEntry:
    id: str
    name: str
    version: str
    file: str
    sha256: str
    size: int
    author: str = ""
    description: str = ""
    category: str = ""


def version_key(version):
    """Sortable form of a version like 1.2.10 so 1.10 is newer than 1.9
    non numeric parts are ignored so use numeric versions in manifests"""
    return tuple(int(part) for part in re.findall(r"\d+", version))


# Network

def _check_url(url):
    """https only except for a local test server"""
    parts = urllib.parse.urlsplit(url)
    local = parts.hostname in ("localhost", "127.0.0.1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise StoreError("The plugin catalog address must use https.")


def _get(url, max_bytes):
    _check_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "shortcuts-app"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            data = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise StoreError("That isn\u2019t in the plugin catalog any more. Try refreshing.") from exc
        raise StoreError(f"The plugin catalog returned an error ({exc.code}). Try again later.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StoreError("Couldn\u2019t reach the plugin catalog. Check your connection.") from exc
    if len(data) > max_bytes:
        raise StoreError("The plugin catalog sent something larger than expected.")
    return data


# Catalog

def _parse_entry(item):
    """CatalogEntry from one index item or None if it is malformed
    a bad item is skipped so one broken plugin never hides the rest"""
    if not isinstance(item, dict):
        return None
    try:
        entry = CatalogEntry(
            id=item["id"], name=item["name"], version=item["version"],
            file=item["file"], sha256=item["sha256"], size=item["size"],
            author=item.get("author") or "", description=item.get("description") or "",
            category=item.get("category") or "",
        )
    except KeyError:
        return None

    text_fields = (entry.id, entry.name, entry.version, entry.file, entry.sha256,
                   entry.author, entry.description, entry.category)
    if not all(isinstance(v, str) for v in text_fields):
        return None
    if isinstance(entry.size, bool) or not isinstance(entry.size, int) or not 0 < entry.size <= _MAX_ZIP_BYTES:
        return None
    if not (_ID_RE.match(entry.id) and _FILE_RE.match(entry.file) and _SHA256_RE.match(entry.sha256)):
        return None
    if not entry.name.strip() or not entry.version.strip():
        return None
    return entry


def fetch_catalog() -> List[CatalogEntry]:
    """Every plugin the catalog offers sorted by name"""
    raw = _get(f"{CATALOG_BASE_URL}/index.json", _MAX_INDEX_BYTES)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise StoreError("The plugin catalog is malformed.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        raise StoreError("The plugin catalog is malformed.")
    if data.get("schema") != _SUPPORTED_SCHEMA:
        raise StoreError("This version of Shortcuts can\u2019t read the plugin catalog. Try updating the app.")

    entries = [e for e in (_parse_entry(item) for item in data["plugins"]) if e is not None]
    entries.sort(key=lambda e: e.name.lower())
    return entries


def download(entry: CatalogEntry) -> str:
    """Downloads and verifies one plugin zip and returns the path of a temp file
    the caller installs it with plugin_manager.install_from_zip on the main thread
    and must delete the file afterwards"""
    data = _get(f"{CATALOG_BASE_URL}/zips/{entry.file}", _MAX_ZIP_BYTES)

    if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
        raise StoreError("The download didn\u2019t match the catalog, so it was discarded. Try again.")

    fd, path = tempfile.mkstemp(prefix="shortcuts-plugin-", suffix=".zip")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        # The zip's own manifest must agree with what the catalog promised
        info = plugin_manager.peek_manifest(path)
        if info.id != entry.id or info.version != entry.version:
            raise StoreError("The download didn\u2019t match the catalog, so it was discarded.")
    except plugin_manager.PluginError as exc:
        _remove_quietly(path)
        raise StoreError(str(exc)) from exc
    except Exception:
        _remove_quietly(path)
        raise
    return path


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


remove_download = _remove_quietly
