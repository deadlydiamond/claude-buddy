"""Command-line interface. Run with no arguments (or the `gui` command) to open the GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core import Paths, copy_sessions, export_to_markdown, fmt_ts, list_accounts, load_sessions, resolve_org


def _paths(args) -> Paths:
    p = Paths()
    if args.app_dir:
        p.app_dir = Path(args.app_dir).expanduser()
    if args.config_dir:
        p.config_dir = Path(args.config_dir).expanduser()
    return p


def cmd_list(args) -> None:
    paths = _paths(args)
    accounts = list_accounts(paths)
    if not accounts:
        sys.exit(f"No Claude desktop Code sessions found in {paths.sessions_dir}")
    for a in accounts:
        print(f"account {a.uuid}{'  (currently signed in)' if a.signed_in else ''}")
        for o in a.orgs:
            arch = sum(s.archived for s in o.sessions)
            print(f"  org {o.uuid}   {len(o.sessions)} sessions ({arch} archived)")
            for s in o.sessions[:3]:
                print(f"      - {s.title}   [{fmt_ts(s.last_activity)}]")
        print()


def cmd_sessions(args) -> None:
    for s in load_sessions(resolve_org(_paths(args), args.src)):
        if s.archived and not args.include_archived:
            continue
        print(f"{s.id}  {fmt_ts(s.last_activity)}  {s.title}{' [archived]' if s.archived else ''}\n    cwd: {s.cwd}")


def cmd_copy(args) -> None:
    paths = _paths(args)
    src, dst = resolve_org(paths, args.src), resolve_org(paths, args.dst)
    sessions = load_sessions(src)
    if args.session:
        picked = [s for s in sessions if any(s.id.startswith(w) or s.id.startswith("local_" + w) for w in args.session)]
    elif args.all:
        picked = [s for s in sessions if args.include_archived or not s.archived]
    else:
        sys.exit("Pass --all or one or more --session IDs (see the `sessions` command)")
    if not picked:
        sys.exit("Nothing to copy")
    copy_sessions(paths, src, dst, picked, share_transcript=args.share_transcript,
                  title_suffix=args.title_suffix, dry_run=args.dry_run)


def cmd_chats(args) -> None:
    export_to_markdown(Path(args.export).expanduser(), Path(args.out).expanduser())
    print("In the other account: create a Project, upload the chats you need and each project's docs,\n"
          "and paste _project.md's instructions into the project's custom instructions.")


def cmd_gui(_args) -> None:
    from .gui import main
    main()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="claude-session-copy",
                                 description="Copy Claude sessions and chats between Claude accounts / organizations.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--app-dir", help="Claude desktop app data folder (auto-detected)")
    ap.add_argument("--config-dir", help="Claude Code config folder, default ~/.claude")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="open the graphical interface (default)").set_defaults(fn=cmd_gui)
    sub.add_parser("list", help="list accounts / orgs with desktop Code sessions").set_defaults(fn=cmd_list)

    sp = sub.add_parser("sessions", help="list sessions in an account/org")
    sp.add_argument("--from", dest="src", required=True, metavar="ACCT/ORG")
    sp.add_argument("--include-archived", action="store_true")
    sp.set_defaults(fn=cmd_sessions)

    cp = sub.add_parser("copy", help="copy sessions to another account/org")
    cp.add_argument("--from", dest="src", required=True, metavar="ACCT/ORG", help="uuid prefixes are fine")
    cp.add_argument("--to", dest="dst", required=True, metavar="ACCT/ORG")
    cp.add_argument("--session", nargs="+", metavar="ID", help="session ids or prefixes")
    cp.add_argument("--all", action="store_true")
    cp.add_argument("--include-archived", action="store_true")
    cp.add_argument("--share-transcript", action="store_true",
                    help="reuse the original transcript instead of cloning it")
    cp.add_argument("--title-suffix", default="")
    cp.add_argument("--dry-run", action="store_true")
    cp.set_defaults(fn=cmd_copy)

    ex = sub.add_parser("chats-to-md", help="convert a claude.ai data export to Markdown")
    ex.add_argument("export", help="export .zip or unzipped folder")
    ex.add_argument("--out", default="claude-chats-md")
    ex.set_defaults(fn=cmd_chats)

    args = ap.parse_args(argv)
    try:
        (getattr(args, "fn", None) or cmd_gui)(args)
    except ValueError as e:
        sys.exit(f"error: {e}")
