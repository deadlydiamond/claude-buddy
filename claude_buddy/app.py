"""Desktop app: a Vue + PrimeVue frontend (claude_buddy/web) in a native pywebview window.

The frontend calls the public methods of `Api` through `window.pywebview.api.<method>(...)`; each call
runs on a worker thread and resolves to the JSON-serialisable value returned here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .names import load_names
from .core import Account, Paths, copy_sessions, export_to_markdown, list_accounts, load_sessions, with_descendants

WEB_DIR = Path(__file__).resolve().parent / "web"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _project_name(cwd: str) -> str:
    if not cwd:
        return ""
    for marker in ("/.claude/worktrees/", "\\.claude\\worktrees\\"):
        if marker in cwd:
            cwd = cwd.split(marker)[0]
    return Path(cwd.rstrip("/\\")).name or cwd


def _codes(accounts: list[Account]) -> dict[str, str]:
    """Shortest unique uppercase prefix (min 4 chars) for every org uuid, used as its display code."""
    uuids = [o.uuid for a in accounts for o in a.orgs]
    n = 4
    while n < 36 and len({u[:n] for u in uuids}) < len(uuids):
        n += 1
    return {u: u[:n].upper() for u in uuids}


class Api:
    def __init__(self) -> None:
        self._paths = Paths()
        self._orgs: dict[str, Path] = {}
        self._window = None

    # ------------------------------------------------------------ state

    def get_state(self) -> dict:
        accounts = list_accounts(self._paths)
        codes = _codes(accounts)
        names = load_names(self._paths.app_dir)
        self._orgs = {}
        orgs = []
        for a in accounts:
            for o in a.orgs:
                self._orgs[o.uuid] = o.path
                info = names.orgs.get(o.uuid)
                orgs.append({
                    "id": o.uuid,
                    "code": codes[o.uuid],
                    "name": info.name if info else None,
                    "plan": info.plan if info else None,
                    "personal": bool(info and info.personal),
                    "account": a.uuid,
                    "accountCode": a.uuid[:4].upper(),
                    "email": names.emails.get(a.uuid),
                    "signedIn": a.signed_in,
                    "sessionCount": len(o.sessions),
                    "latestTitle": o.sessions[0].title if o.sessions else "",
                    "lastActivity": o.sessions[0].last_activity if o.sessions else 0,
                })
        return {
            "version": __version__,
            "appDir": str(self._paths.app_dir),
            "configDir": str(self._paths.config_dir),
            "found": self._paths.sessions_dir.is_dir(),
            "multipleAccounts": len(accounts) > 1,
            "orgs": orgs,
        }

    def get_sessions(self, org_id: str) -> list[dict]:
        sessions = load_sessions(self._org(org_id))
        synced = self._synced_elsewhere(org_id)
        return [{
            "id": s.id,
            "title": s.title,
            "project": _project_name(s.cwd),
            "cwd": s.cwd,
            "lastActivity": s.last_activity,
            "archived": s.archived,
            "parentId": s.parent_id,
            "syncedWith": sorted(synced.get(s.data.get("cliSessionId"), ())),
        } for s in sessions]

    def _synced_elsewhere(self, org_id: str) -> dict[str, set[str]]:
        """transcript id -> labels of *other* orgs that have a session on the same transcript."""
        accounts = list_accounts(self._paths)
        codes = _codes(accounts)
        names = load_names(self._paths.app_dir)
        out: dict[str, set[str]] = {}
        for a in accounts:
            for o in a.orgs:
                if o.uuid == org_id:
                    continue
                info = names.orgs.get(o.uuid)
                label = info.name if info else codes[o.uuid]
                for s in o.sessions:
                    cli = s.data.get("cliSessionId")
                    if cli:
                        out.setdefault(cli, set()).add(label)
        return out

    def set_folders(self, app_dir: str, config_dir: str) -> dict:
        self._paths = Paths(Path(app_dir).expanduser(), Path(config_dir).expanduser())
        return self.get_state()

    # ------------------------------------------------------------ actions

    def copy(self, src_id: str, dst_id: str, session_ids: list[str], title_suffix: str = "", sync: bool = False) -> dict:
        """sync=True: both orgs share one transcript, so work continues across them (one at a time)."""
        src, dst = self._org(src_id), self._org(dst_id)
        # Sub-sessions always travel with their parent.
        sessions = with_descendants(load_sessions(src), session_ids)
        lines: list[str] = []
        copied = copy_sessions(self._paths, src, dst, sessions, share_transcript=sync, title_suffix=title_suffix,
                               log=lines.append)
        return {"copied": copied, "missingTranscripts": sum("NOT found" in l for l in lines)}

    def convert_export(self, export_path: str) -> dict:
        export = Path(export_path).expanduser()
        base = export.with_suffix("") if export.is_file() else export
        out = base.with_name(base.name + "-markdown")
        chats, projects = export_to_markdown(export, out, log=lambda _m: None)
        return {"chats": chats, "projects": projects, "out": str(out)}

    # ------------------------------------------------------------ OS helpers

    def pick_folder(self, start: str = "") -> str | None:
        res = self._win().create_file_dialog(20, directory=start or str(Path.home()))  # FileDialog.FOLDER
        return res[0] if res else None

    def pick_export(self) -> str | None:
        res = self._win().create_file_dialog(10, directory=str(Path.home() / "Downloads"),  # FileDialog.OPEN
                                             file_types=("Zip archive (*.zip)", "All files (*.*)"))
        return res[0] if res else None

    def reveal(self, path: str) -> None:
        p = str(Path(path).expanduser())
        if sys.platform == "darwin":
            subprocess.Popen(["open", p])
        elif sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", p])

    def open_url(self, url: str) -> None:
        if url.startswith("https://"):
            webbrowser.open(url)

    def claude_running(self) -> bool:
        try:
            if sys.platform.startswith("win"):
                out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Claude.exe"], capture_output=True, text=True,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
                return "Claude.exe" in out
            return subprocess.run(["pgrep", "-x", "Claude"], capture_output=True).returncode == 0
        except OSError:
            return False

    # ------------------------------------------------------------ internals

    def _org(self, org_id: str) -> Path:
        if not self._orgs:
            self.get_state()
        if org_id not in self._orgs:
            raise ValueError("That organization is no longer on this computer. Refresh and try again.")
        return self._orgs[org_id]

    def _win(self):
        import webview
        return self._window or webview.windows[0]


def main() -> None:
    import webview

    index = WEB_DIR / "index.html"
    if not index.exists():
        sys.exit(f"Frontend not built: {index} is missing. Run `npm ci && npm run build` in ./frontend first.")
    api = Api()
    api._window = webview.create_window("Claude Buddy", str(index), js_api=api, width=1080, height=760,
                                        min_size=(820, 600), background_color="#ECEFF3")
    # Window / Dock / taskbar icon (packaged builds also embed it via PyInstaller --icon).
    icon = ASSETS_DIR / ("icon.ico" if sys.platform.startswith("win") else "icon.png")
    webview.start(debug=bool(os.environ.get("CLAUDE_BUDDY_DEBUG")), icon=str(icon) if icon.exists() else None)
