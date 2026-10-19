# Claude Session Copy

A small desktop app (with a CLI) that copies your **Claude** sessions and chats to a **different Claude organization or a different Claude account**.

- **Claude Code sessions** from the Claude desktop app (the *Code* tab) are copied directly, including the full conversation history, so you can keep working on them in the other account or org.
- **claude.ai chats** can't be imported into another account (Claude has no import feature). The app turns your official data export into tidy Markdown files that you upload to a Project in the new account.

> Unofficial tool, not affiliated with Anthropic. It works with the Claude desktop app's local files, whose layout may change between app versions. Your original sessions are never modified.

## Download

Grab the latest build from the [**Releases**](https://github.com/shivanshtalwar0/claude-session-copy/releases/latest) page:

| Platform | File |
| --- | --- |
| Windows 10/11 | `ClaudeSessionCopy-windows-x64.exe` |
| macOS (Apple Silicon, M1 or later) | `ClaudeSessionCopy-macos-apple-silicon.zip` |
| macOS (Intel) | `ClaudeSessionCopy-macos-intel.zip` |
| Linux x64 | `ClaudeSessionCopy-linux-x64.tar.gz` |

The builds aren't code-signed, so your OS will warn the first time:

- **macOS:** unzip, then right-click **Claude Session Copy.app → Open → Open**. If it says the app is damaged, run `xattr -dr com.apple.quarantine "Claude Session Copy.app"` once.
- **Windows:** if SmartScreen appears, click **More info → Run anyway**.
- **Linux:** `tar -xzf ClaudeSessionCopy-linux-x64.tar.gz && ./claude-session-copy`

## Copy Claude Code sessions to another account or org

1. **Sign in to the target account/org once** in the Claude desktop app, so the app creates its local folder. Then switch back to wherever you like.
2. Open **Claude Session Copy** and select the **Code sessions** tab.
3. Under **Copy from**, pick the account/org that has the sessions. The currently signed-in account is marked with `*`, and each entry shows its session count and latest session title to help you tell them apart.
4. Under **Copy to**, pick the destination.
5. Select sessions in the list. Use Search, Cmd/Ctrl-click and Shift-click, or **Select all**.
6. Optional: tick **Dry run** to preview without writing anything.
7. Click **Copy selected sessions**.
8. **Restart the Claude desktop app** and switch to the target account/org. The copies appear in the sidebar, titled with the suffix you chose, " (copied)" by default.

### What gets copied

| Copied | Not copied (the app rebuilds these for the new org) |
| --- | --- |
| Full conversation transcript, including subagent and tool files | Connector / MCP settings from the old org |
| Title, project folder, model, effort, permission mode | Cloud environments, remote-control links |
| Linked PRs, branches, archived state | Links to other sessions, pending errors |

Each copy gets fresh IDs and its own copy of the transcript, so continuing it in one place never affects the other. If you'd rather both entries share one transcript, use **Share transcript with original (advanced)**.

## Move claude.ai chats to another account

1. In the **old** account: claude.ai → **Settings → Privacy → Export data**. You'll get an email with a `.zip`.
2. In Claude Session Copy, open the **claude.ai chats** tab, choose the `.zip`, pick an output folder and click **Convert to Markdown**.
3. In the **new** account: create a Project and upload the chats you need from the `chats/` folder. For each folder under `projects/`, create a project, upload its files, and paste `_project.md` into the project instructions.

Claude can then read and continue from that history. The chats won't appear as native chat history, because Claude doesn't allow importing that.

## Command line

Requires Python 3.9+ and no other dependencies.

```bash
git clone https://github.com/shivanshtalwar0/claude-session-copy && cd claude-session-copy
python3 -m claude_session_copy                      # opens the GUI
python3 -m claude_session_copy list                 # accounts / orgs and their sessions
python3 -m claude_session_copy sessions --from a575/a117
python3 -m claude_session_copy copy --from a575/a117 --to c30a/b91a --all --dry-run
python3 -m claude_session_copy copy --from a575/a117 --to c30a/b91a --session 02d2dd1a 5ad1af4c
python3 -m claude_session_copy chats-to-md ~/Downloads/claude-export.zip --out claude-chats-md
```

`ACCOUNT/ORG` take unique prefixes of the folder UUIDs shown by `list`. Other `copy` options are `--include-archived`, `--title-suffix " (copied)"` and `--share-transcript`. Use `--app-dir` / `--config-dir` if your data lives somewhere non-standard.

## How it works

The Claude desktop app keeps Code sessions in

```
<app data>/claude-code-sessions/<account-uuid>/<org-uuid>/local_<id>.json   session metadata
<app data>/claude-code-sessions/<account-uuid>/<org-uuid>/archived-sessions.idx
~/.claude/projects/<project-folder-slug>/<transcript-id>.jsonl              conversation transcript
```

where `<app data>` is `~/Library/Application Support/Claude` on macOS, `%APPDATA%\Claude` on Windows, and `~/.config/Claude` on Linux.

Copying a session clones its metadata into the target `<account>/<org>` folder under a new ID, drops fields tied to the old org, and clones the transcript under a new transcript ID.

Sessions started from the `claude` command in a terminal aren't tied to an account at all. `claude --resume` already works after you switch accounts.

## Build from source

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ClaudeSessionCopy run.py
```

Use a Python with Tk 8.6 or newer (python.org installers, `uv python install`, or `actions/setup-python`). On macOS, Apple's built-in Tk 8.5 makes text widgets spin the CPU. GitHub Actions builds every platform on each push and publishes a release when a `v*` tag is pushed.

## License

MIT
