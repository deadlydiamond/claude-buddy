"""
Core logic for copying Claude desktop Code sessions between accounts / organizations and for
converting a claude.ai data export into Markdown.

How the Claude desktop app stores Code sessions:
    <app data>/claude-code-sessions/<account-uuid>/<org-uuid>/local_<id>.json   session metadata
    <app data>/claude-code-sessions/<account-uuid>/<org-uuid>/archived-sessions.idx
    <claude config>/projects/<cwd-slug>/<cli-session-id>.jsonl                   transcript
    <claude config>/projects/<cwd-slug>/<cli-session-id>/                        sidecar files

The transcript is not tied to an account, the metadata is. Copying a session clones the metadata
into the target <account>/<org> folder and clones the transcript under a fresh id.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

Log = Callable[[str], None]

# Session fields that point at org/account-scoped state (connectors, environments, other sessions,
# cached prompts) or are transient UI/error state. They are dropped from the copy; the app rebuilds them.
DROP_FIELDS = {
    "remoteMcpServersConfig", "enabledMcpTools", "envScopeId", "startedFromEnvironmentId",
    "error", "errorAt", "errorRows", "priorErrorMark", "interruptedAwaitingPerson",
    "sideSessionNotes", "backgroundTaskSuggestions", "resolvedBackgroundTaskSuggestions",
    "peerReceipts", "peerMessaged", "sideSessionWakesSinceUserMessage", "steeredByRemoteClient",
    "remoteControlAutoEligible", "lastTurnCutShort", "latestUserFrameAt", "lastSpawnRootDetected",
    "spawnSeed", "promptAppendSnapshot", "toolSurfaceSnapshot", "turnBoxDeclared", "turnBoxMounted",
    "bridgeSessionId", "remoteSessionId", "parentSessionId", "queuedSideSessionNotes", "pendingSystemReminder",
}

# Fields that link a session to the session it was started from (sub-sessions and forks).
PARENT_FIELDS = ("spawnedFrom", "forkedFromSessionId")


# ---------------------------------------------------------------- locations

def default_app_dir() -> Path:
    if env := os.environ.get("CLAUDE_APP_DIR"):
        return Path(env)
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Claude"
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "Claude"


def default_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


@dataclass
class Paths:
    app_dir: Path = field(default_factory=default_app_dir)
    config_dir: Path = field(default_factory=default_config_dir)

    @property
    def sessions_dir(self) -> Path:
        return self.app_dir / "claude-code-sessions"

    @property
    def projects_dir(self) -> Path:
        return self.config_dir / "projects"


# ---------------------------------------------------------------- model

@dataclass
class Session:
    path: Path
    data: dict
    archived: bool

    @property
    def id(self) -> str:
        return self.data.get("sessionId") or self.path.stem

    @property
    def title(self) -> str:
        return self.data.get("title") or "(untitled)"

    @property
    def cwd(self) -> str:
        return self.data.get("cwd") or ""

    @property
    def last_activity(self) -> int:
        return self.data.get("lastActivityAt") or self.data.get("createdAt") or 0

    @property
    def parent_id(self) -> str | None:
        """The session this one was started from (a sub-session) or forked from, if any."""
        spawned = self.data.get("spawnedFrom")
        if isinstance(spawned, dict) and spawned.get("sessionId"):
            return spawned["sessionId"]
        return self.data.get("forkedFromSessionId") or None


@dataclass
class Org:
    account: str
    uuid: str
    path: Path
    sessions: list[Session]

    @property
    def label(self) -> str:
        n = len(self.sessions)
        recent = f' - latest: "{self.sessions[0].title[:40]}"' if self.sessions else ""
        return f"org {self.uuid[:8]}  ({n} session{'s' if n != 1 else ''}){recent}"


@dataclass
class Account:
    uuid: str
    signed_in: bool
    orgs: list[Org]


def fmt_ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M") if ms else "-"


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json_atomic(p: Path, data) -> None:
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def archived_ids(org_dir: Path) -> set[str]:
    data = _read_json(org_dir / "archived-sessions.idx", {}) or {}
    return set(data.get("archived") or [])


def load_sessions(org_dir: Path) -> list[Session]:
    arch = archived_ids(org_dir)
    out = []
    for f in org_dir.glob("local_*.json"):
        data = _read_json(f)
        if isinstance(data, dict):
            out.append(Session(f, data, bool(data.get("isArchived")) or data.get("sessionId") in arch))
    out.sort(key=lambda s: s.last_activity, reverse=True)
    return out


def list_accounts(paths: Paths) -> list[Account]:
    if not paths.sessions_dir.is_dir():
        return []
    cfg = _read_json(paths.app_dir / "config.json", {}) or {}
    current = cfg.get("lastKnownAccountUuid")
    accounts = []
    for acct in sorted(p for p in paths.sessions_dir.iterdir() if p.is_dir()):
        orgs = [Org(acct.name, o.name, o, load_sessions(o))
                for o in sorted(p for p in acct.iterdir() if p.is_dir())]
        accounts.append(Account(acct.name, acct.name == current, orgs))
    accounts.sort(key=lambda a: not a.signed_in)
    return accounts


def resolve_org(paths: Paths, spec: str) -> Path:
    """Resolve 'ACCOUNT/ORG' (unique uuid prefixes allowed) to an org folder."""
    if "/" not in spec:
        raise ValueError(f"expected ACCOUNT/ORG, got '{spec}'")
    acct, org = spec.split("/", 1)

    def pick(parent: Path, prefix: str, what: str) -> Path:
        if not parent.is_dir():
            raise ValueError(f"{parent} does not exist")
        hits = [p for p in parent.iterdir() if p.is_dir() and p.name.startswith(prefix)]
        if not hits:
            raise ValueError(f"no {what} matching '{prefix}'")
        if len(hits) > 1:
            raise ValueError(f"'{prefix}' is ambiguous: {', '.join(h.name for h in hits)}")
        return hits[0]

    return pick(pick(paths.sessions_dir, acct, "account"), org, "org")


# ---------------------------------------------------------------- session trees

def children_map(sessions: Iterable[Session]) -> dict[str, list[Session]]:
    """parent id -> direct sub-sessions, for parents present in `sessions`."""
    sessions = list(sessions)
    ids = {s.id for s in sessions}
    kids: dict[str, list[Session]] = {}
    for s in sessions:
        if s.parent_id in ids and s.parent_id != s.id:
            kids.setdefault(s.parent_id, []).append(s)
    return kids


def with_descendants(all_sessions: Iterable[Session], selected_ids: Iterable[str]) -> list[Session]:
    """The selected sessions plus every sub-session below them, parents before children."""
    all_sessions = list(all_sessions)
    by_id = {s.id: s for s in all_sessions}
    kids = children_map(all_sessions)
    out: list[Session] = []
    seen: set[str] = set()

    def visit(sid: str) -> None:
        if sid in seen or sid not in by_id:
            return
        seen.add(sid)
        out.append(by_id[sid])
        for k in kids.get(sid, []):
            visit(k.id)

    for sid in selected_ids:
        visit(sid)
    return out


# ---------------------------------------------------------------- copy

def cwd_slug(cwd: str) -> str:
    # Claude Code names project folders after the cwd with every non-alphanumeric char -> '-'
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def find_transcript(paths: Paths, cli_id: str, cwd: str | None) -> Path | None:
    if cwd:
        p = paths.projects_dir / cwd_slug(cwd) / f"{cli_id}.jsonl"
        if p.exists():
            return p
    if not paths.projects_dir.is_dir():
        return None
    return next(iter(paths.projects_dir.glob(f"*/{cli_id}.jsonl")), None)


def _clone_transcript(old_id: str, new_id: str, src: Path) -> None:
    dst = src.with_name(f"{new_id}.jsonl")
    with src.open("r", encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            fout.write(line.replace(old_id, new_id))
    side = src.with_name(old_id)
    if side.is_dir():
        new_side = src.with_name(new_id)
        shutil.copytree(side, new_side)
        for p in new_side.rglob("*"):
            if p.is_file() and p.suffix in (".json", ".jsonl", ".txt", ".md"):
                try:
                    p.write_text(p.read_text(encoding="utf-8").replace(old_id, new_id), encoding="utf-8")
                except UnicodeDecodeError:
                    pass


def copy_sessions(paths: Paths, src_dir: Path, dst_dir: Path, sessions: Iterable[Session], *,
                  share_transcript: bool = False, title_suffix: str = "", dry_run: bool = False,
                  log: Log = print) -> int:
    if src_dir.resolve() == dst_dir.resolve():
        raise ValueError("source and target are the same org")
    sessions = list(sessions)
    prefix = "[dry run] " if dry_run else ""
    log(f"{prefix}Copying {len(sessions)} session(s)\n  from {src_dir}\n  to   {dst_dir}")

    # New ids up front, so sub-sessions can point at their parent's copy.
    new_ids = {s.id: f"local_{uuid.uuid4()}" for s in sessions}

    copied, newly_archived = 0, []
    for s in sessions:
        new_local = new_ids[s.id]
        new = {k: v for k, v in s.data.items() if k not in DROP_FIELDS}
        new["sessionId"] = new_local
        parent = s.parent_id
        if parent in new_ids:
            if isinstance(new.get("spawnedFrom"), dict):
                new["spawnedFrom"] = {**new["spawnedFrom"], "sessionId": new_ids[parent]}
            if new.get("forkedFromSessionId"):
                new["forkedFromSessionId"] = new_ids[parent]
        else:
            # The parent isn't being copied, so it won't exist in the target org.
            for k in PARENT_FIELDS:
                new.pop(k, None)
        if title_suffix:
            new["title"] = s.title + title_suffix
        new["copiedFrom"] = {"sessionId": s.id, "org": src_dir.name, "account": src_dir.parent.name,
                             "at": int(time.time() * 1000)}

        note = "no transcript id"
        old_cli = s.data.get("cliSessionId")
        if old_cli:
            src_tr = find_transcript(paths, old_cli, s.cwd)
            if src_tr is None:
                note = "transcript NOT found (metadata only)"
            elif share_transcript:
                note = "sharing the original transcript"
            else:
                new_cli = str(uuid.uuid4())
                if not dry_run:
                    _clone_transcript(old_cli, new_cli, src_tr)
                new["cliSessionId"] = new_cli
                note = "transcript cloned"

        if not dry_run:
            _write_json_atomic(dst_dir / f"{new_local}.json", new)
        if s.archived:
            newly_archived.append(new_local)
        copied += 1
        log(f"  {'  - ' if parent in new_ids else '+ '}{s.title}  ({note})")

    if newly_archived and not dry_run:
        idx = dst_dir / "archived-sessions.idx"
        data = _read_json(idx, None) or {"v": 1, "archived": []}
        data["archived"] = list(dict.fromkeys((data.get("archived") or []) + newly_archived))
        _write_json_atomic(idx, data)

    log(f"{prefix}{'Would copy' if dry_run else 'Copied'} {copied} session(s).")
    if not dry_run and copied:
        log("Restart the Claude desktop app and switch to the target account/org to see them.")
    return copied


# ---------------------------------------------------------------- claude.ai export -> markdown

def _msg_text(m: dict) -> str:
    parts = []
    for c in m.get("content") or []:
        t = c.get("type")
        if t == "text" and c.get("text"):
            parts.append(c["text"])
        elif t == "tool_use":
            parts.append(f"*[tool call: {c.get('name')}]*")
        elif t == "tool_result":
            parts.append("*[tool result]*")
        # "thinking" blocks are skipped
    if not parts and m.get("text"):
        parts.append(m["text"])
    for a in m.get("attachments") or []:
        body, name = a.get("extracted_content"), a.get("file_name") or "attachment"
        parts.append(f"<details><summary>Attachment: {name}</summary>\n\n{body}\n\n</details>" if body
                     else f"*[attachment: {name}]*")
    for fl in m.get("files") or m.get("files_v2") or []:
        parts.append(f"*[file: {fl.get('file_name') or fl.get('file_uuid')}]*")
    return "\n\n".join(parts).strip()


def _safe(name: str) -> str:
    return (re.sub(r"[^\w\- .]+", "", name).strip() or "untitled")[:80]


def _load_export(path: Path) -> tuple[list, list]:
    def read(name):
        if path.is_dir():
            hits = list(path.rglob(name))
            return json.loads(hits[0].read_text(encoding="utf-8")) if hits else []
        with zipfile.ZipFile(path) as z:
            hits = [n for n in z.namelist() if n.endswith(name)]
            return json.loads(z.read(hits[0]).decode("utf-8")) if hits else []
    return read("conversations.json"), read("projects.json")


def export_to_markdown(export: Path, out: Path, log: Log = print) -> tuple[int, int]:
    if not export.exists():
        raise ValueError(f"{export} not found")
    convs, projects = _load_export(export)
    if not convs and not projects:
        raise ValueError("no conversations.json / projects.json found in the export")
    (out / "chats").mkdir(parents=True, exist_ok=True)

    index = ["# Claude chat export", ""]
    for c in sorted(convs, key=lambda c: c.get("updated_at") or "", reverse=True):
        name = c.get("name") or "untitled"
        date = (c.get("created_at") or "")[:10]
        fname = f"{date} {_safe(name)} {(c.get('uuid') or '')[:8]}.md".strip()
        lines = [f"# {name}", "", f"- created: {c.get('created_at')}", f"- updated: {c.get('updated_at')}",
                 f"- original id: {c.get('uuid')}", ""]
        for m in c.get("chat_messages") or []:
            text = _msg_text(m)
            if text:
                lines += [f"## {'User' if m.get('sender') == 'human' else 'Claude'}", "", text, ""]
        (out / "chats" / fname).write_text("\n".join(lines), encoding="utf-8")
        index.append(f"- [{name}](chats/{fname.replace(' ', '%20')}) - {date}")

    for p in projects:
        pdir = out / "projects" / _safe(p.get("name") or p.get("uuid") or "project")
        pdir.mkdir(parents=True, exist_ok=True)
        meta = [f"# {p.get('name')}", "", p.get("description") or "", ""]
        if p.get("prompt_template"):
            meta += ["## Project instructions", "", p["prompt_template"], ""]
        (pdir / "_project.md").write_text("\n".join(meta), encoding="utf-8")
        for d in p.get("docs") or []:
            (pdir / _safe(d.get("filename") or d.get("uuid") or "doc")).write_text(d.get("content") or "",
                                                                                   encoding="utf-8")

    (out / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    log(f"Wrote {len(convs)} chat(s) and {len(projects)} project(s) to {out}")
    return len(convs), len(projects)
