"""Tkinter GUI for Claude Session Copy."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import Org, Paths, copy_sessions, export_to_markdown, fmt_ts, list_accounts

APP_TITLE = "Claude Session Copy"


def open_folder(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        elif sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError:
        pass


def claude_is_running() -> bool:
    try:
        if sys.platform.startswith("win"):
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Claude.exe"], capture_output=True, text=True,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            return "Claude.exe" in out
        return subprocess.run(["pgrep", "-x", "Claude"], capture_output=True).returncode == 0
    except OSError:
        return False


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} {__version__}")
        self.geometry("1040x720")
        self.minsize(820, 560)
        if sys.platform.startswith("linux"):
            ttk.Style(self).theme_use("clam")

        self.paths = Paths()
        self.orgs: dict[str, Org] = {}
        self.log_q: queue.Queue[str] = queue.Queue()
        self.busy = False

        self.app_dir_var = tk.StringVar(value=str(self.paths.app_dir))
        self.cfg_dir_var = tk.StringVar(value=str(self.paths.config_dir))
        self.src_var, self.dst_var = tk.StringVar(), tk.StringVar()
        self.filter_var = tk.StringVar()
        self.show_archived = tk.BooleanVar(value=False)
        self.suffix_var = tk.StringVar(value=" (copied)")
        self.dry_run = tk.BooleanVar(value=False)
        self.share_tr = tk.BooleanVar(value=False)
        self.count_var = tk.StringVar(value="0 selected")
        self.export_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(Path.home() / "Desktop" / "claude-chats-md"))

        self._build()
        self.after(100, self._drain_log)
        self.refresh()

    # ------------------------------------------------------------ layout

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}

        folders = ttk.LabelFrame(self, text="Claude data folders (auto-detected)")
        folders.pack(fill="x", **pad)
        for row, (label, var, which) in enumerate([("Desktop app data:", self.app_dir_var, "app"),
                                                   ("Claude Code data:", self.cfg_dir_var, "cfg")]):
            ttk.Label(folders, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            ttk.Entry(folders, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6, pady=2)
            ttk.Button(folders, text="Change...", command=lambda w=which: self._pick_data_dir(w)).grid(
                row=row, column=2, padx=6, pady=2)
        ttk.Button(folders, text="Refresh", command=self.refresh).grid(row=0, column=3, rowspan=2, padx=6)
        folders.columnconfigure(1, weight=1)

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, **pad)

        nb = ttk.Notebook(paned)
        paned.add(nb, weight=4)
        nb.add(self._build_sessions_tab(nb), text="  Code sessions  ")
        nb.add(self._build_chats_tab(nb), text="  claude.ai chats  ")

        logf = ttk.LabelFrame(paned, text="Log")
        paned.add(logf, weight=1)
        self.log_text = tk.Text(logf, height=8, wrap="word", state="disabled", font=("TkFixedFont", 11))
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb.pack(side="right", fill="y", pady=6)

    def _build_sessions_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=8)

        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Copy from:").grid(row=0, column=0, sticky="w")
        self.src_cb = ttk.Combobox(top, textvariable=self.src_var, state="readonly")
        self.src_cb.grid(row=0, column=1, sticky="ew", padx=6, pady=2)
        self.src_cb.bind("<<ComboboxSelected>>", lambda _e: self._fill_tree())
        ttk.Label(top, text="Copy to:").grid(row=1, column=0, sticky="w")
        self.dst_cb = ttk.Combobox(top, textvariable=self.dst_var, state="readonly")
        self.dst_cb.grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        top.columnconfigure(1, weight=1)
        ttk.Label(top, foreground="gray",
                  text="An account/org shows up here after you have signed into it once in the Claude desktop app."
                  ).grid(row=2, column=1, sticky="w", padx=6)

        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 4))
        ttk.Label(bar, text="Search:").pack(side="left")
        ent = ttk.Entry(bar, textvariable=self.filter_var, width=30)
        ent.pack(side="left", padx=6)
        self.filter_var.trace_add("write", lambda *_: self._fill_tree())
        ttk.Checkbutton(bar, text="Show archived", variable=self.show_archived,
                        command=self._fill_tree).pack(side="left", padx=6)
        ttk.Label(bar, textvariable=self.count_var).pack(side="right")
        ttk.Button(bar, text="Select none", command=lambda: self.tree.selection_set(())).pack(side="right", padx=4)
        ttk.Button(bar, text="Select all", command=lambda: self.tree.selection_set(self.tree.get_children())
                   ).pack(side="right", padx=4)

        tf = ttk.Frame(f)
        tf.pack(fill="both", expand=True)
        cols = ("title", "last", "folder", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for c, text, w, stretch in [("title", "Session", 360, True), ("last", "Last activity", 130, False),
                                    ("folder", "Project folder", 340, True), ("status", "", 70, False)]:
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, stretch=stretch, anchor="w")
        vsb = ttk.Scrollbar(tf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.count_var.set(f"{len(self.tree.selection())} selected"))

        opts = ttk.Frame(f)
        opts.pack(fill="x", pady=(8, 0))
        ttk.Label(opts, text="Add to copied titles:").pack(side="left")
        ttk.Entry(opts, textvariable=self.suffix_var, width=14).pack(side="left", padx=6)
        ttk.Checkbutton(opts, text="Dry run (preview only)", variable=self.dry_run).pack(side="left", padx=8)
        ttk.Checkbutton(opts, text="Share transcript with original (advanced)",
                        variable=self.share_tr).pack(side="left", padx=8)
        self.copy_btn = ttk.Button(opts, text="Copy selected sessions  ->", command=self.do_copy)
        self.copy_btn.pack(side="right")
        return f

    def _build_chats_tab(self, parent) -> ttk.Frame:
        f = ttk.Frame(parent, padding=12)
        steps = (
            "claude.ai chats are stored on Anthropic's servers and cannot be imported into another account.\n"
            "This turns your official data export into readable Markdown files you can upload to a Project "
            "in the other account.\n\n"
            "1.  In the OLD account open claude.ai -> Settings -> Privacy -> Export data, and download the .zip "
            "from the email.\n"
            "2.  Choose that .zip below and press Convert.\n"
            "3.  In the NEW account create a Project, upload the chats you need from the 'chats' folder, and for "
            "each folder under 'projects' upload its files and paste _project.md into the project instructions."
        )
        ttk.Label(f, text=steps, justify="left", wraplength=900).grid(row=0, column=0, columnspan=4, sticky="w",
                                                                      pady=(0, 14))
        ttk.Label(f, text="Export (.zip or folder):").grid(row=1, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.export_var).grid(row=1, column=1, sticky="ew", padx=6, pady=3)
        ttk.Button(f, text="Choose .zip...", command=self._pick_export_zip).grid(row=1, column=2, padx=3)
        ttk.Button(f, text="Choose folder...", command=self._pick_export_dir).grid(row=1, column=3, padx=3)
        ttk.Label(f, text="Save Markdown to:").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.out_var).grid(row=2, column=1, sticky="ew", padx=6, pady=3)
        ttk.Button(f, text="Choose...", command=self._pick_out).grid(row=2, column=2, padx=3)
        btns = ttk.Frame(f)
        btns.grid(row=3, column=1, sticky="w", pady=12)
        self.convert_btn = ttk.Button(btns, text="Convert to Markdown", command=self.do_convert)
        self.convert_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Open output folder",
                   command=lambda: open_folder(Path(self.out_var.get()).expanduser())).pack(side="left")
        f.columnconfigure(1, weight=1)
        return f

    # ------------------------------------------------------------ data

    def refresh(self) -> None:
        self.paths = Paths(Path(self.app_dir_var.get()).expanduser(), Path(self.cfg_dir_var.get()).expanduser())
        self.orgs.clear()
        for acct in list_accounts(self.paths):
            for org in acct.orgs:
                star = "*  " if acct.signed_in else "   "
                who = "signed-in account" if acct.signed_in else "account"
                self.orgs[f"{star}{who} {acct.uuid[:8]}  /  {org.label}"] = org
        labels = list(self.orgs)
        self.src_cb["values"] = labels
        self.dst_cb["values"] = labels
        if labels:
            if self.src_var.get() not in labels:
                self.src_var.set(labels[0])
            if self.dst_var.get() not in labels:
                self.dst_var.set(labels[1] if len(labels) > 1 else "")
            self.log(f"Found {len(labels)} account/org combination(s) in {self.paths.sessions_dir}")
        else:
            self.src_var.set("")
            self.dst_var.set("")
            self.log(f"No Claude desktop Code sessions found in {self.paths.sessions_dir}. "
                     "Is the Claude desktop app installed and signed in? You can point to the folder above.")
        self._fill_tree()

    def _fill_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        org = self.orgs.get(self.src_var.get())
        if not org:
            self.count_var.set("0 selected")
            return
        q = self.filter_var.get().strip().lower()
        for i, s in enumerate(org.sessions):
            if s.archived and not self.show_archived.get():
                continue
            if q and q not in s.title.lower() and q not in s.cwd.lower():
                continue
            self.tree.insert("", "end", iid=str(i),
                             values=(s.title, fmt_ts(s.last_activity), s.cwd, "archived" if s.archived else ""))
        self.count_var.set("0 selected")

    # ------------------------------------------------------------ actions

    def do_copy(self) -> None:
        if self.busy:
            return
        src, dst = self.orgs.get(self.src_var.get()), self.orgs.get(self.dst_var.get())
        if not src or not dst:
            messagebox.showwarning(APP_TITLE, "Choose both a source and a target account/org.")
            return
        if src.path == dst.path:
            messagebox.showwarning(APP_TITLE, "Source and target are the same. Pick a different target.")
            return
        sel = [src.sessions[int(i)] for i in self.tree.selection()]
        if not sel:
            messagebox.showinfo(APP_TITLE, "Select one or more sessions in the list first (Ctrl/Cmd-click or "
                                           "Shift-click to select several, or press Select all).")
            return
        dry = self.dry_run.get()
        if not dry:
            warn = ("\n\nThe Claude desktop app is running. Restart it after copying so the sessions show up."
                    if claude_is_running() else "")
            if not messagebox.askyesno(APP_TITLE, f"Copy {len(sel)} session(s)?\n\nFrom: {self.src_var.get().strip()}"
                                                  f"\nTo:   {self.dst_var.get().strip()}\n\nOriginals are not "
                                                  f"changed.{warn}"):
                return

        def work():
            try:
                copy_sessions(self.paths, src.path, dst.path, sel, share_transcript=self.share_tr.get(),
                              title_suffix=self.suffix_var.get(), dry_run=dry, log=self.log)
                if not dry:
                    self.after(0, self.refresh)
            except Exception as e:  # noqa: BLE001 - surface anything to the user
                self.log(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror(APP_TITLE, str(e)))

        self._run(work, self.copy_btn)

    def do_convert(self) -> None:
        if self.busy:
            return
        export = Path(self.export_var.get()).expanduser()
        out = Path(self.out_var.get()).expanduser()
        if not self.export_var.get() or not export.exists():
            messagebox.showwarning(APP_TITLE, "Choose your claude.ai export (.zip or unzipped folder) first.")
            return

        def work():
            try:
                export_to_markdown(export, out, log=self.log)
                self.after(0, lambda: open_folder(out))
            except Exception as e:  # noqa: BLE001
                self.log(f"ERROR: {e}")
                self.after(0, lambda: messagebox.showerror(APP_TITLE, str(e)))

        self._run(work, self.convert_btn)

    def _run(self, fn, button: ttk.Button) -> None:
        self.busy = True
        button.state(["disabled"])

        def wrapper():
            try:
                fn()
            finally:
                self.busy = False
                self.after(0, lambda: button.state(["!disabled"]))

        threading.Thread(target=wrapper, daemon=True).start()

    # ------------------------------------------------------------ pickers / log

    def _pick_data_dir(self, which: str) -> None:
        var = self.app_dir_var if which == "app" else self.cfg_dir_var
        d = filedialog.askdirectory(initialdir=var.get() or str(Path.home()))
        if d:
            var.set(d)
            self.refresh()

    def _pick_export_zip(self) -> None:
        p = filedialog.askopenfilename(filetypes=[("Zip archive", "*.zip"), ("All files", "*")])
        if p:
            self.export_var.set(p)

    def _pick_export_dir(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.export_var.set(p)

    def _pick_out(self) -> None:
        p = filedialog.askdirectory()
        if p:
            self.out_var.set(p)

    def log(self, msg: str) -> None:
        self.log_q.put(msg)

    def _drain_log(self) -> None:
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)


def main() -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
