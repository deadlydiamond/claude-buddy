import tempfile
import unittest
from pathlib import Path

from claude_buddy.names import _unsnappy, load_names

ORG_TEAM = b"a1173955-722b-4fe6-bad2-741f8a61d4a4"
ORG_PERSONAL = b"fc1a760d-280f-4f4d-8574-6d756c80d2ae"
CHAT = b"0bb10688-0000-4000-8000-000000000000"
ACCOUNT = b"a575bae2-6cc6-4ea2-8a25-526edffd112b"


def key(k: bytes) -> bytes:
    return b'"' + bytes([len(k)]) + k


def s(v: bytes) -> bytes:
    return b'"' + bytes([len(v)]) + v


def org(uid: bytes, name: bytes, caps: list[bytes], raven: bytes | None) -> bytes:
    arr = b"a" + bytes([len(caps)]) + b"".join(b"I" + bytes([i * 2]) + s(c) for i, c in enumerate(caps)) + b"@\x02\x02"
    out = key(b"uuid") + s(uid) + key(b"name") + s(name) + key(b"capabilities") + arr
    if raven:
        out += key(b"raven_type") + s(raven)
    return out + b"{\x10"


class NamesTest(unittest.TestCase):
    def test_unsnappy_literal_and_copy(self):
        self.assertEqual(_unsnappy(b"\x09\x08abc\x09\x03"), b"abcabcabc")

    def test_load_names_from_cache_blob(self):
        blob = (key(b"account") + b"o" + key(b"uuid") + s(ACCOUNT) + key(b"email_address") + s(b"me@example.com")
                + key(b"memberships") + org(ORG_TEAM, b"Developers-77o", [b"chat", b"raven"], b"team")
                + org(ORG_PERSONAL, b"me@example.com's Organization", [b"chat", b"claude_max"], None)
                + key(b"uuid") + s(CHAT) + key(b"name") + s(b"A chat title"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "IndexedDB" / "https_claude.ai_0.indexeddb.blob" / "1" / "a6"
            p.mkdir(parents=True)
            (p / "a61d").write_bytes(blob)
            names = load_names(Path(d))
        self.assertEqual(names.emails[ACCOUNT.decode()], "me@example.com")
        team, personal = names.orgs[ORG_TEAM.decode()], names.orgs[ORG_PERSONAL.decode()]
        self.assertEqual((team.name, team.plan, team.personal), ("Developers-77o", "Team", False))
        self.assertEqual((personal.name, personal.plan, personal.personal), ("Personal", "Max", True))
        self.assertNotIn(CHAT.decode(), names.orgs)

    def test_garbled_values_are_ignored(self):
        blob = key(b"uuid") + s(ACCOUNT) + key(b"email_address") + s(b'sh)\x01@I(Do.com" full')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "IndexedDB" / "https_claude.ai_0.indexeddb.blob" / "1"
            p.mkdir(parents=True)
            (p / "x").write_bytes(b"membership" + blob)
            self.assertEqual(load_names(Path(d)).emails, {})

    def test_missing_cache_is_harmless(self):
        with tempfile.TemporaryDirectory() as d:
            names = load_names(Path(d))
        self.assertEqual((names.orgs, names.emails), ({}, {}))


if __name__ == "__main__":
    unittest.main()
