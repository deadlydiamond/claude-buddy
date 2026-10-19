import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from claude_session_copy.core import (Paths, copy_sessions, cwd_slug, export_to_markdown, list_accounts, load_sessions,
                                      with_descendants)

OLD_CLI = "11111111-2222-3333-4444-555555555555"


class CopySessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = Paths(root / "app", root / "cfg")
        self.src = self.paths.sessions_dir / "acctA" / "orgA"
        self.dst = self.paths.sessions_dir / "acctB" / "orgB"
        self.src.mkdir(parents=True)
        self.dst.mkdir(parents=True)
        (self.paths.app_dir / "config.json").write_text(json.dumps({"lastKnownAccountUuid": "acctA"}))

        cwd = "/home/me/project"
        for sid, title in [("local_a", "First"), ("local_b", "Archived one")]:
            (self.src / f"{sid}.json").write_text(json.dumps({
                "sessionId": sid, "cliSessionId": OLD_CLI if sid == "local_a" else None, "cwd": cwd,
                "title": title, "lastActivityAt": 1, "envScopeId": "org-specific", "enabledMcpTools": {"x": True},
            }))
        (self.src / "archived-sessions.idx").write_text(json.dumps({"v": 1, "archived": ["local_b"]}))

        proj = self.paths.projects_dir / cwd_slug(cwd)
        proj.mkdir(parents=True)
        (proj / f"{OLD_CLI}.jsonl").write_text(
            "\n".join(json.dumps({"sessionId": OLD_CLI, "n": i}) for i in range(5)) + "\n")
        (proj / OLD_CLI).mkdir()
        (proj / OLD_CLI / "custom-title.json").write_text(json.dumps({"sessionId": OLD_CLI}))
        self.proj = proj

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_accounts(self):
        accounts = list_accounts(self.paths)
        self.assertEqual([a.uuid for a in accounts], ["acctA", "acctB"])
        self.assertTrue(accounts[0].signed_in)
        self.assertEqual(len(accounts[0].orgs[0].sessions), 2)

    def test_copy(self):
        sessions = load_sessions(self.src)
        n = copy_sessions(self.paths, self.src, self.dst, sessions, title_suffix=" (copy)", log=lambda _m: None)
        self.assertEqual(n, 2)

        copied = {s.data["copiedFrom"]["sessionId"]: s for s in load_sessions(self.dst)}
        first, arch = copied["local_a"], copied["local_b"]
        self.assertEqual(first.title, "First (copy)")
        self.assertNotIn("envScopeId", first.data)
        self.assertNotIn("enabledMcpTools", first.data)
        self.assertTrue(arch.archived)
        self.assertFalse(first.archived)

        new_cli = first.data["cliSessionId"]
        self.assertNotEqual(new_cli, OLD_CLI)
        lines = [json.loads(l) for l in (self.proj / f"{new_cli}.jsonl").read_text().splitlines()]
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(l["sessionId"] == new_cli for l in lines))
        self.assertEqual(json.loads((self.proj / new_cli / "custom-title.json").read_text())["sessionId"], new_cli)
        # originals untouched
        self.assertIn(OLD_CLI, (self.proj / f"{OLD_CLI}.jsonl").read_text())
        self.assertEqual(len(load_sessions(self.src)), 2)

    def test_dry_run_writes_nothing(self):
        copy_sessions(self.paths, self.src, self.dst, load_sessions(self.src), dry_run=True, log=lambda _m: None)
        self.assertEqual(list(self.dst.iterdir()), [])
        self.assertEqual(len(list(self.proj.glob("*.jsonl"))), 1)

    def _add(self, sid, **extra):
        (self.src / f"{sid}.json").write_text(json.dumps({"sessionId": sid, "title": sid, "cwd": "/x", **extra}))

    def test_sub_sessions_follow_parent(self):
        self._add("local_p")
        self._add("local_c1", spawnedFrom={"sessionId": "local_p", "taskId": "t1", "title": "p"})
        self._add("local_c2", spawnedFrom={"sessionId": "local_p"})
        self._add("local_g", forkedFromSessionId="local_c1")
        self._add("local_other", spawnedFrom={"sessionId": "local_a"})
        sessions = load_sessions(self.src)

        picked = with_descendants(sessions, ["local_p"])
        self.assertEqual({s.id for s in picked}, {"local_p", "local_c1", "local_c2", "local_g"})
        self.assertEqual(picked[0].id, "local_p")

        copy_sessions(self.paths, self.src, self.dst, picked, log=lambda _m: None)
        new = {s.data["copiedFrom"]["sessionId"]: s for s in load_sessions(self.dst)}
        self.assertEqual(new["local_c1"].parent_id, new["local_p"].id)
        self.assertEqual(new["local_c2"].parent_id, new["local_p"].id)
        self.assertEqual(new["local_c1"].data["spawnedFrom"]["taskId"], "t1")
        self.assertEqual(new["local_g"].parent_id, new["local_c1"].id)

    def test_child_copied_alone_loses_dangling_link(self):
        self._add("local_c", spawnedFrom={"sessionId": "local_a"})
        child = [s for s in load_sessions(self.src) if s.id == "local_c"]
        copy_sessions(self.paths, self.src, self.dst, child, log=lambda _m: None)
        (copy,) = load_sessions(self.dst)
        self.assertIsNone(copy.parent_id)
        self.assertNotIn("spawnedFrom", copy.data)

    def test_same_org_rejected(self):
        with self.assertRaises(ValueError):
            copy_sessions(self.paths, self.src, self.src, [], log=lambda _m: None)


class ExportTest(unittest.TestCase):
    def test_export_to_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            conv = [{"uuid": "abcdef12-0", "name": "Trip: Goa", "created_at": "2026-09-01T00:00:00Z",
                     "chat_messages": [
                         {"sender": "human", "content": [{"type": "text", "text": "Plan a trip"}],
                          "attachments": [{"file_name": "n.txt", "extracted_content": "budget"}]},
                         {"sender": "assistant", "content": [{"type": "thinking", "thinking": "secret"},
                                                             {"type": "text", "text": "Day 1"}]}]}]
            proj = [{"name": "P1", "prompt_template": "Be brief", "docs": [{"filename": "spec.md", "content": "x"}]}]
            with zipfile.ZipFile(d / "export.zip", "w") as z:
                z.writestr("conversations.json", json.dumps(conv))
                z.writestr("projects.json", json.dumps(proj))
            n_chats, n_proj = export_to_markdown(d / "export.zip", d / "out", log=lambda _m: None)
            self.assertEqual((n_chats, n_proj), (1, 1))
            md = next((d / "out" / "chats").glob("*.md")).read_text()
            self.assertIn("Plan a trip", md)
            self.assertIn("budget", md)
            self.assertIn("Day 1", md)
            self.assertNotIn("secret", md)
            self.assertIn("Be brief", (d / "out" / "projects" / "P1" / "_project.md").read_text())


if __name__ == "__main__":
    unittest.main()
