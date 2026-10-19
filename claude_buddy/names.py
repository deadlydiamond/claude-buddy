"""
Best-effort lookup of human-readable account and organization names ("Developers-77o · Team",
"Personal · Max", "you@example.com") from the Claude desktop app's local web cache.

The desktop app caches claude.ai's account data in Chromium IndexedDB. Large values live as files under
IndexedDB/https_claude.ai_0.indexeddb.blob/, Snappy-compressed V8-serialised objects. We only read
strings out of them (no network, no tokens, no cookies). Any failure just means names are unavailable
and the UI falls back to short org codes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

UUID_RE = rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _clean(text: str | None) -> bool:
    return bool(text) and text.isprintable() and len(text) <= 200
MAX_FILE = 64 * 1024 * 1024


@dataclass
class OrgInfo:
    name: str
    plan: str        # "Team", "Enterprise", "Max", "Pro", "Free" or ""
    personal: bool


@dataclass
class Names:
    orgs: dict[str, OrgInfo]
    emails: dict[str, str]   # account uuid -> email


# ---------------------------------------------------------------- decoding

def _varint(b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def _unsnappy(b: bytes, i: int = 0) -> bytes:
    """Raw Snappy decompression (no framing)."""
    n, i = _varint(b, i)
    if n > 512 * 1024 * 1024:
        raise ValueError("implausible length")
    out = bytearray()
    end = len(b)
    while i < end and len(out) < n:
        t = b[i]
        i += 1
        kind = t & 3
        if kind == 0:
            ln = t >> 2
            if ln >= 60:
                nb = ln - 59
                ln = int.from_bytes(b[i:i + nb], "little")
                i += nb
            ln += 1
            out += b[i:i + ln]
            i += ln
            continue
        if kind == 1:
            ln = ((t >> 2) & 7) + 4
            off = ((t >> 5) << 8) | b[i]
            i += 1
        elif kind == 2:
            ln = (t >> 2) + 1
            off = int.from_bytes(b[i:i + 2], "little")
            i += 2
        else:
            ln = (t >> 2) + 1
            off = int.from_bytes(b[i:i + 4], "little")
            i += 4
        if off == 0 or off > len(out):
            raise ValueError("bad back-reference")
        if off >= ln:
            start = len(out) - off
            out += out[start:start + ln]
        else:
            for _ in range(ln):
                out.append(out[-off])
    if len(out) != n:
        raise ValueError("length mismatch")
    return bytes(out)


def _payload(raw: bytes) -> bytes:
    """Snappy-decoded contents if the value is compressed, else the bytes as-is.

    Never scan compressed bytes directly: literal fragments survive compression and would
    produce garbled matches (half an email address, say)."""
    for start in range(0, 8):
        try:
            return _unsnappy(raw, start)
        except (ValueError, IndexError):
            continue
    return raw


def _key(k: bytes) -> bytes:
    return b'"' + bytes([len(k)]) + k   # V8 one-byte string


def _read_str(d: bytes, i: int) -> tuple[str | None, int]:
    while i < len(d) and d[i] == 0:      # alignment padding before two-byte strings
        i += 1
    if i >= len(d) or d[i] not in (0x22, 0x63, 0x53):
        return None, i
    n, j = _varint(d, i + 1)
    enc = {0x22: "latin-1", 0x63: "utf-16-le", 0x53: "utf-8"}[d[i]]
    return d[j:j + n].decode(enc, "replace"), j + n


# ---------------------------------------------------------------- extraction

def _plan(caps: list[str], raven_type: str | None) -> str:
    if "raven" in caps:
        return (raven_type or "team").replace("_", " ").title()
    if "claude_max" in caps:
        return "Max"
    if "claude_pro" in caps:
        return "Pro"
    return "Free" if caps else ""


def _scan(d: bytes, names: Names) -> None:
    k_uuid, k_name, k_email = _key(b"uuid"), _key(b"name"), _key(b"email_address")
    k_caps, k_raven = _key(b"capabilities"), _key(b"raven_type")
    for m in re.finditer(re.escape(k_uuid) + rb'"\$(' + UUID_RE + rb")", d):
        uid = m.group(1).decode()
        j = m.end()
        if d.startswith(k_email, j) and uid not in names.emails:
            email, _ = _read_str(d, j + len(k_email))
            if email and EMAIL_RE.fullmatch(email):
                names.emails[uid] = email
        elif d.startswith(k_name, j) and uid not in names.orgs:
            name, k = _read_str(d, j + len(k_name))
            if not _clean(name):
                continue
            window = d[k:k + 40000]
            nxt = window.find(k_uuid + b'"$')       # stay inside this organization object
            if nxt > 0:
                window = window[:nxt]
            caps: list[str] = []
            c = window.find(k_caps)
            if c >= 0:
                seg = window[c + len(k_caps):c + len(k_caps) + 400].split(b"@")[0]
                caps = [x.decode() for x in re.findall(rb'"[\x01-\x60]([a-z0-9_:]+)', seg)]
            if not caps:
                continue                            # chats share this shape; organizations have capabilities
            raven = None
            r = window.find(k_raven)
            if r >= 0:
                raven, _ = _read_str(window, r + len(k_raven))
            personal = "raven" not in caps and name.endswith("'s Organization")
            names.orgs[uid] = OrgInfo("Personal" if personal else name, _plan(caps, raven), personal)


_cache: dict[tuple, Names] = {}


def load_names(app_dir: Path) -> Names:
    names = Names({}, {})
    base = app_dir / "IndexedDB"
    try:
        files = [p for p in base.glob("https_claude.ai_*.indexeddb.blob/**/*") if p.is_file()]
        files += [p for p in base.glob("https_claude.ai_*.indexeddb.leveldb/*.log") if p.is_file()]
    except OSError:
        return names
    sig = tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files))
    if sig in _cache:
        return _cache[sig]
    for p in sorted(files, key=lambda p: p.stat().st_mtime_ns, reverse=True):   # newest first
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            raw = p.read_bytes()
        except OSError:
            continue
        if b"membership" not in raw and b"email_address" not in raw:
            continue
        try:
            _scan(_payload(raw), names)
        except (IndexError, ValueError):
            continue
    _cache.clear()
    _cache[sig] = names
    return names
