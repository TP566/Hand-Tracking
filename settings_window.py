"""Settings window: a Tkinter editor for config.json, run as its own process.

It only edits and saves the file (through ``config_store``); the running app
notices the change and applies the live settings itself. ``main.py`` imports
this module just for ``launch_settings``, so nothing here creates Tk at import.
"""

import copy
import math
import subprocess
import sys
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import config_store
from actions import ACTION_TYPES
from hand_signs import GESTURES
from instance import LOCK_PATH, ROOT, app_running
from learned_signs import NONE_LABEL, SIGN_NAME

RESTART_FIELDS = (("camera_index", "Camera index"), ("width", "Camera width"),
                  ("height", "Camera height"), ("camera_fps", "Camera fps"), ("fps", "Output fps"))
GENERAL_LIVE_FIELDS = (("quality", "Quality"), ("show_preview", "Show preview"),
                       ("preview_width", "Preview width"), ("mirror_preview", "Mirror preview"))
SIGN_FIELDS = (("hold_frames", "Hold frames"), ("miss_tolerance", "Miss tolerance (frames)"),
               ("cooldown_sec", "Cooldown (seconds)"))
BOOL_KEYS = ("show_preview", "mirror_preview")
# What main.py assumes when a key is missing; camera_fps falls back to fps.
DEFAULTS = {"miss_tolerance": 3, "quality": "auto", "show_preview": True,
            "preview_width": 640, "mirror_preview": True}
DOMAIN_FIELDS = (("title", "Title"), ("video", "Video"), ("keywords", "Keywords"),
                 ("loop_start_sec", "Loop start (s)"), ("loop_end_sec", "Loop end (s)"),
                 ("hotkey", "Hotkey"))
HINTS = {"title": "empty = the sign name", "keywords": "comma-separated, to find the video",
         "loop_end_sec": "empty = to the end", "hotkey": "e.g. <ctrl>+<alt>+d"}
CHANGED_MESSAGE = ("config.json was changed outside this window. "
                   "Reload it? (Your unsaved edits will be lost)")
ERROR_COLOR = "#c62828"
HINT_COLOR = "#666666"
REFRESH_MS = 2000
START_GRACE_SEC = 15     # the app takes a while to load before it holds the lock


def interpreter(name: str) -> str:
    """``name`` (python.exe or pythonw.exe) from the running interpreter's folder, else that interpreter."""
    path = Path(sys.executable).with_name(name)
    return str(path) if path.exists() else sys.executable


def launch_settings() -> None:
    """Open the settings window in its own process and return at once.

    It runs detached under pythonw.exe, so closing the app's console leaves it open.
    """
    subprocess.Popen([interpreter("pythonw.exe"), str(Path(__file__).resolve())],
                     cwd=ROOT, creationflags=subprocess.DETACHED_PROCESS)


def to_number(text: str, integer: bool):
    """``text`` as an int (when ``integer``) or float; the stripped text if it is not a number."""
    text = text.strip()
    for convert in ((int, float) if integer else (float,)):
        try:
            value = convert(text)
        except ValueError:
            continue
        if math.isfinite(value):
            return value
    return text


def video_value(path: str) -> str:
    """A chosen video as stored in config.json: relative to the project folder when inside it."""
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(Path(path))


def restart_keys(old: dict, new: dict) -> list[str]:
    """Changed keys that the running app only picks up on restart."""
    keys = list(old) + [key for key in new if key not in old]
    return [key for key in keys if key not in config_store.LIVE_KEYS and old.get(key) != new.get(key)]


def scrollable(parent: tk.Widget) -> ttk.Frame:
    """A frame inside a vertically scrolling canvas, packed into ``parent``."""
    canvas = tk.Canvas(parent, highlightthickness=0, height=380)
    bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas)
    item = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(item, width=e.width))
    canvas.configure(yscrollcommand=bar.set)
    wheel = lambda e: canvas.yview_scroll(-e.delta // 120, "units")
    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    return inner


@dataclass
class ActionRow:
    original: str | None            # the saved sign name; None for a row added in this window
    base: dict                      # the saved action, to keep keys this window does not edit
    sign: tk.StringVar
    kind: tk.StringVar
    value: tk.StringVar
    error: tk.StringVar
    sign_box: ttk.Combobox
    widgets: list[tk.Widget] = field(default_factory=list)


class SettingsWindow:
    """The settings editor; ``collect`` and ``save`` work without the window being shown."""

    def __init__(self, root: tk.Tk, config_path: Path, samples_dir: Path):
        self.root = root
        self.config_path = config_path
        self.samples_dir = samples_dir
        self.cfg, self.mtime = config_store.load(config_path)
        self.fields: dict[str, tk.Variable] = {}
        self.errors: dict[str, str] = {}
        self.error_vars: dict[str, tk.StringVar] = {}
        self.domains: dict[str, dict[str, tk.StringVar]] = {}
        self.rename_buttons: dict[str, ttk.Button] = {}
        self.action_rows: list[ActionRow] = []
        self.status = tk.StringVar(root)
        self.hold_seconds = tk.StringVar(root)
        self._start_grace = 0.0

        root.title("Hand Tracking settings")
        root.minsize(620, 520)
        self.notebook = ttk.Notebook(root)
        self.tabs = {name: ttk.Frame(self.notebook, padding=10)
                     for name in ("General", "Signs", "Domains", "Actions")}
        for name, tab in self.tabs.items():
            self.notebook.add(tab, text=name)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        bar = ttk.Frame(root, padding=(8, 4, 8, 8))
        bar.pack(fill="x")
        self.start_button = ttk.Button(bar, text="Start app", command=self.start_app)
        self.start_button.pack(side="right")
        ttk.Button(bar, text="Save", command=self.save).pack(side="right", padx=6)
        ttk.Label(bar, textvariable=self.status, wraplength=420).pack(side="left", fill="x")
        root.bind("<Control-s>", lambda e: self.save())
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._populate()
        self._poll_start()

    # ---- building the tabs ----

    def _populate(self) -> None:
        """Rebuild every tab from ``self.cfg``."""
        for tab in self.tabs.values():
            for child in tab.winfo_children():
                child.destroy()
        self.fields, self.error_vars, self.domains, self.rename_buttons = {}, {}, {}, {}
        self.action_rows = []
        self._errors_below: list[tuple[ttk.Label, tk.StringVar]] = []
        self._domain_base: dict[str, dict] = dict(self.cfg.get("domains", {}))
        self._domain_frames: dict[str, ttk.LabelFrame] = {}
        self._build_general()
        self._build_signs()
        self._build_domains()
        self._build_actions()
        # Compared with collect(), not cfg, so defaults filled in for missing keys are not edits.
        self._pristine = self.collect()

    def _error_label(self, parent: tk.Widget, path: str) -> ttk.Label:
        var = tk.StringVar(self.root)
        self.error_vars[path] = var
        return ttk.Label(parent, textvariable=var, foreground=ERROR_COLOR)

    def _error_below(self, parent: tk.Widget, var: tk.StringVar, row: int, columnspan: int) -> None:
        """An error line under a field that only takes up space while it has a message."""
        label = ttk.Label(parent, textvariable=var, foreground=ERROR_COLOR)
        label.grid(row=row, column=0, columnspan=columnspan, sticky="w", padx=(0, 6))
        label.grid_remove()
        self._errors_below.append((label, var))

    def _loaded_or_default(self, key: str):
        """The value from config.json, or what main.py assumes when the key is missing."""
        if key in self.cfg:
            return self.cfg[key]
        return {**DEFAULTS, "camera_fps": self.cfg.get("fps", "")}.get(key, "")

    def _section(self, tab: ttk.Frame, header: str, specs) -> ttk.LabelFrame:
        box = ttk.LabelFrame(tab, text=header, padding=8)
        box.pack(fill="x", pady=(0, 8))
        for row, (key, label) in enumerate(specs):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            value = self._loaded_or_default(key)
            if key in BOOL_KEYS:
                var = tk.BooleanVar(self.root, value=bool(value))
                widget = ttk.Checkbutton(box, variable=var)
            elif key == "quality":
                var = tk.StringVar(self.root, value=str(value))
                widget = ttk.Combobox(box, textvariable=var, values=config_store.QUALITIES,
                                      state="readonly", width=8)
            else:
                var = tk.StringVar(self.root, value=str(value))
                widget = ttk.Entry(box, textvariable=var, width=10)
            widget.grid(row=row, column=1, sticky="w", pady=2)
            self.fields[key] = var
            self._error_label(box, key).grid(row=row, column=3, sticky="w", padx=8)
        return box

    def _build_general(self) -> None:
        tab = self.tabs["General"]
        self._section(tab, "Applies on restart", RESTART_FIELDS)
        self._section(tab, "Live", GENERAL_LIVE_FIELDS)

    def _build_signs(self) -> None:
        tab = self.tabs["Signs"]
        box = self._section(tab, "Live", SIGN_FIELDS)
        ttk.Label(box, textvariable=self.hold_seconds).grid(row=0, column=2, sticky="w", padx=4)
        self.fields["hold_frames"].trace_add("write", self._update_seconds)
        self._update_seconds()
        ttk.Label(tab, foreground=HINT_COLOR, wraplength=520, justify="left", text=(
            "Hold frames: how long a sign must be held before it fires (the app runs at 30 "
            "frames a second). Miss tolerance: frames the hand may drop out without resetting "
            "the hold. Cooldown: wait after a sign fires before it can fire again.")).pack(anchor="w")

    def _update_seconds(self, *_) -> None:
        value = to_number(self.fields["hold_frames"].get(), integer=True)
        self.hold_seconds.set(f"≈ {value / 30:.1f} s" if not isinstance(value, str) else "")

    def _build_domains(self) -> None:
        box = ttk.LabelFrame(self.tabs["Domains"], text="Applies on restart", padding=8)
        box.pack(fill="both", expand=True)
        top = ttk.Frame(box)
        top.pack(fill="x", pady=(0, 6))
        ttk.Button(top, text="Add Domain", command=self._ask_add_domain).pack(side="left")
        ttk.Label(top, text="Renaming a Domain also moves its recordings in samples/.",
                  foreground=HINT_COLOR).pack(side="left", padx=8)
        self._domain_list = scrollable(box)
        for name in self._domain_base:
            self._domain_section(name)

    def _domain_section(self, name: str) -> None:
        built_in = name in GESTURES
        box = ttk.LabelFrame(self._domain_list, padding=8,
                             text=f"{name} (built-in sign)" if built_in else name)
        box.pack(fill="x", pady=4, padx=(0, 4))
        box.columnconfigure(1, weight=1)
        self._domain_frames[name] = box
        base = self._domain_base[name]
        vars_ = {}
        for index, (key, label) in enumerate(DOMAIN_FIELDS):
            row = 2 * index
            value = base.get(key)
            if key == "keywords" and isinstance(value, list):
                text = ", ".join(map(str, value))
            else:
                text = "" if value is None else str(value)
            vars_[key] = var = tk.StringVar(self.root, value=text)
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            ttk.Entry(box, textvariable=var, width=34).grid(row=row, column=1, sticky="we", pady=2)
            if key == "video":
                ttk.Button(box, text="Browse…", command=lambda v=var: self._browse(v)).grid(
                    row=row, column=2, sticky="w", padx=4)
            elif key in HINTS:
                ttk.Label(box, text=HINTS[key], foreground=HINT_COLOR).grid(
                    row=row, column=2, sticky="w", padx=4)
            path = f"domains.{name}.{key}"
            self.error_vars[path] = tk.StringVar(self.root)
            self._error_below(box, self.error_vars[path], row + 1, 3)
        buttons = ttk.Frame(box)
        buttons.grid(row=2 * len(DOMAIN_FIELDS), column=0, columnspan=4, sticky="w", pady=(6, 0))
        if not built_in:
            self.rename_buttons[name] = ttk.Button(
                buttons, text="Rename…", command=lambda: self._ask_rename("domain", name))
            self.rename_buttons[name].pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Remove", command=lambda: self._ask_remove_domain(name)).pack(side="left")
        self._error_label(buttons, f"domains.{name}").pack(side="left", padx=8)
        self.domains[name] = vars_

    def _build_actions(self) -> None:
        box = ttk.LabelFrame(self.tabs["Actions"], text="Live", padding=8)
        box.pack(fill="both", expand=True)
        self._action_list = ttk.Frame(box)
        self._action_list.pack(fill="x")
        for column, text in enumerate(("Sign", "Action", "Value")):
            ttk.Label(self._action_list, text=text).grid(row=0, column=column, sticky="w")
        self._next_action_row = 1
        self._sign_names = config_store.known_signs(self.cfg, self.samples_dir)
        for name, action in self.cfg.get("actions", {}).items():
            action = action if isinstance(action, dict) else {}
            kind = next((k for k in ACTION_TYPES if k in action), "keys")
            self._action_row(name, kind, str(action.get(kind, "")), name, action)
        ttk.Button(box, text="Add action", command=self.add_action).pack(anchor="w", pady=(8, 4))
        ttk.Label(box, foreground=HINT_COLOR, wraplength=520, justify="left", text=(
            "keys: a shortcut such as ctrl+shift+f9.  type: text to type.  open: an app, file or "
            "website.  To use a new sign, teach it with teach.bat <name>.")).pack(anchor="w")

    def add_action(self, name: str = "", kind: str = "keys", value: str = "") -> None:
        self._action_row(name, kind, value, None, {})

    def _action_row(self, name: str, kind: str, value: str, original: str | None, base: dict) -> None:
        r, parent = self._next_action_row, self._action_list
        self._next_action_row += 2
        sign = tk.StringVar(self.root, value=name)
        box = ttk.Combobox(parent, textvariable=sign, values=self._sign_names, width=20,
                           state="disabled" if original else "normal")
        # Re-read on opening the list, so a sign taught while the window is open shows up.
        box.configure(postcommand=lambda: box.configure(
            values=config_store.known_signs(self.cfg, self.samples_dir)))
        row = ActionRow(original, base, sign, tk.StringVar(self.root, value=kind),
                        tk.StringVar(self.root, value=value), tk.StringVar(self.root), box)
        row.widgets = [box,
                       ttk.Combobox(parent, textvariable=row.kind, values=ACTION_TYPES,
                                    state="readonly", width=6),
                       ttk.Entry(parent, textvariable=row.value, width=30)]
        if original and original not in GESTURES:
            row.widgets.append(ttk.Button(parent, text="Rename…",
                                          command=lambda: self._ask_rename("action", original)))
        else:
            row.widgets.append(ttk.Frame(parent))
        row.widgets.append(ttk.Button(parent, text="Remove", command=lambda: self._remove_action(row)))
        for column, widget in enumerate(row.widgets):
            widget.grid(row=r, column=column, sticky="w", padx=(0, 6), pady=2)
        self._error_below(parent, row.error, r + 1, len(row.widgets))
        row.widgets.append(self._errors_below[-1][0])
        self.action_rows.append(row)

    def _remove_action(self, row: ActionRow) -> None:
        for widget in row.widgets:
            widget.destroy()
        self.action_rows.remove(row)

    # ---- reading the widgets ----

    def collect(self) -> dict:
        """The config built from the widgets, on top of the loaded one (unknown keys kept)."""
        cfg = copy.deepcopy(self.cfg)
        for key, var in self.fields.items():
            if key in BOOL_KEYS:
                cfg[key] = bool(var.get())
            elif key == "quality":
                cfg[key] = var.get()
            else:
                integer = (key in config_store.INTEGER_KEYS
                           or type(self._loaded_or_default(key)) is int)
                cfg[key] = to_number(var.get(), integer)
        cfg["domains"] = {name: self._collect_domain(name, vars_)
                          for name, vars_ in self.domains.items()}
        if "actions" in cfg or self.action_rows:
            cfg["actions"] = {}
            for row in self.action_rows:
                action = {k: v for k, v in copy.deepcopy(row.base).items() if k not in ACTION_TYPES}
                action[row.kind.get()] = row.value.get()
                cfg["actions"][row.sign.get().strip()] = action
        return cfg

    def _collect_domain(self, name: str, vars_: dict[str, tk.StringVar]) -> dict:
        domain = copy.deepcopy(self._domain_base[name])
        text = {key: var.get() for key, var in vars_.items()}
        start, end = domain.get("loop_start_sec"), domain.get("loop_end_sec")
        values = {
            "title": text["title"],
            "video": text["video"].strip(),
            "keywords": [w.strip() for w in text["keywords"].split(",") if w.strip()],
            "loop_start_sec": to_number(text["loop_start_sec"], type(start) is int),
            "loop_end_sec": (to_number(text["loop_end_sec"], type(end) is int)
                             if text["loop_end_sec"].strip() else None),
            "hotkey": text["hotkey"].strip(),
        }
        for key, value in values.items():
            # Optional keys that were absent stay absent while left empty.
            if key in domain or key in ("loop_start_sec", "hotkey") or value not in ("", [], None):
                domain[key] = value
        return domain

    def _dirty(self) -> bool:
        return self.collect() != self._pristine

    # ---- actions ----

    def save(self) -> bool:
        """Validate, write config.json and report; False (nothing written) on any problem."""
        cfg = self.collect()
        self.errors = config_store.validate(cfg)
        names = [row.sign.get().strip() for row in self.action_rows]
        for name in {n for n in names if names.count(n) > 1}:
            self.errors[f"actions.{name}"] = "Two actions use this sign; remove one."
        self._show_errors()
        if self.errors:
            return False
        try:
            self.mtime = config_store.save(self.config_path, cfg, self.mtime)
        except config_store.ConfigChanged:
            if messagebox.askyesno("Reload settings?", CHANGED_MESSAGE):
                self.reload()
            else:
                self.status.set("Not saved.")
            return False
        except OSError as exc:
            messagebox.showerror("Not saved", f"Could not save {self.config_path.name}: {exc}")
            return False
        restart = restart_keys(self.cfg, cfg)
        self.cfg = cfg
        self._populate()
        self.status.set(f"Saved. Restart the app to apply: {', '.join(restart)}" if restart
                        else "Saved. Live settings applied.")
        return True

    def _show_errors(self) -> None:
        for path, var in self.error_vars.items():
            var.set(self.errors.get(path, ""))
        for row in self.action_rows:
            row.error.set(self.errors.get(f"actions.{row.sign.get().strip()}", ""))
        self._errors_below = [(label, var) for label, var in self._errors_below if label.winfo_exists()]
        for label, var in self._errors_below:
            if var.get():
                label.grid()
            else:
                label.grid_remove()
        if not self.errors:
            return
        shown = set(self.error_vars) | {f"actions.{row.sign.get().strip()}" for row in self.action_rows}
        tabs = []
        for path in self.errors:
            section = path.split(".")[0]
            tab = {"domains": "Domains", "actions": "Actions"}.get(section, (
                "Signs" if section in dict(SIGN_FIELDS) else "General"))
            if tab not in tabs:
                tabs.append(tab)
        others = [f"{path}: {message}" for path, message in self.errors.items() if path not in shown]
        self.status.set(" ".join([f"Not saved. Fix the fields marked in red ({', '.join(tabs)})."]
                                 + others))

    def reload(self) -> None:
        """Throw away unsaved edits and show config.json as it is on disk."""
        try:
            self.cfg, self.mtime = config_store.load(self.config_path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not reload", f"Could not read {self.config_path.name}: {exc}")
            return
        self.errors = {}
        self._populate()
        self.status.set(f"Reloaded {self.config_path.name}.")

    def add_domain(self, name: str) -> bool:
        """Add an empty Domain section (saved with the next Save)."""
        name = name.strip()
        used = set(self.domains) | {row.sign.get().strip() for row in self.action_rows} | {NONE_LABEL}
        if not SIGN_NAME.match(name):
            messagebox.showerror("Add Domain", "Name may only use letters, numbers and underscores.")
            return False
        if name in used:
            messagebox.showerror("Add Domain", f"The name {name} is already used; pick a different one.")
            return False
        self._domain_base[name] = {"title": name.replace("_", " ").title(), "video": "",
                                   "keywords": [], "loop_start_sec": 0.0, "loop_end_sec": None,
                                   "hotkey": ""}
        self._domain_section(name)
        hint = "" if (self.samples_dir / name).is_dir() else f" Teach its sign with teach.bat {name}."
        self.status.set(f"Added {name}: set its hotkey and video, then Save.{hint}")
        return True

    def remove_domain(self, name: str) -> None:
        """Drop a Domain section (saved with the next Save); its recordings stay in samples/."""
        self._domain_frames.pop(name).destroy()
        for table in (self.domains, self._domain_base, self.rename_buttons):
            table.pop(name, None)
        prefix = f"domains.{name}"
        for path in [p for p in self.error_vars if p == prefix or p.startswith(prefix + ".")]:
            del self.error_vars[path]
        self.status.set(f"Removed {name}. Save to apply.")

    def rename(self, kind: str, old: str, new: str) -> bool:
        """Rename a Domain or action and its recordings right away (it saves config.json)."""
        if self._dirty():
            if not messagebox.askokcancel("Unsaved changes", (
                    f"Renaming {old} saves config.json. Save your other changes first?")):
                return False
            if not self.save():
                return False
        try:
            self.cfg, self.mtime = config_store.rename_sign(
                self.cfg, kind, old, new, self.config_path, self.samples_dir, self.mtime)
        except config_store.RenameError as exc:
            messagebox.showerror("Could not rename", str(exc))
            return False
        self._populate()
        self.status.set(f"Renamed {old} to {new}. Restart the app to apply the new name.")
        return True

    def refresh_start(self) -> None:
        """Enable Start app only while the app is not running (or just being started)."""
        busy = app_running(LOCK_PATH) or time.monotonic() < self._start_grace
        self.start_button.configure(state="disabled" if busy else "normal")

    def _poll_start(self) -> None:
        self.refresh_start()
        self.root.after(REFRESH_MS, self._poll_start)

    def start_app(self) -> None:
        if self._dirty():
            answer = messagebox.askyesnocancel("Unsaved changes", "Save your changes before starting the app?")
            if answer is None or (answer and not self.save()):
                return
        # Through run.bat in a new console: the app gets one even when this window runs under
        # pythonw.exe, and run.bat's pause keeps it open to show why the app could not start.
        subprocess.Popen(["cmd.exe", "/c", str(ROOT / "run.bat")], cwd=ROOT,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
        self._start_grace = time.monotonic() + START_GRACE_SEC
        self.refresh_start()
        self.status.set("Starting the app in its own window…")

    # ---- dialogs ----

    def _ask_add_domain(self) -> None:
        name = simpledialog.askstring("Add Domain", "Sign name for the new Domain "
                                      "(letters, numbers and _):", parent=self.root)
        if name:
            self.add_domain(name)

    def _ask_remove_domain(self, name: str) -> None:
        if messagebox.askyesno("Remove Domain", f"Remove the Domain {name}? "
                               "Its recordings in samples/ are kept."):
            self.remove_domain(name)

    def _ask_rename(self, kind: str, old: str) -> None:
        new = simpledialog.askstring("Rename", f"New sign name for {old}:", initialvalue=old,
                                     parent=self.root)
        if new and new.strip() != old:
            self.rename(kind, old, new.strip())

    def _browse(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, initialdir=ROOT / "videos", title="Choose the Domain video",
            filetypes=[("Videos", "*.mp4 *.mkv *.webm *.mov *.avi"), ("All files", "*.*")])
        if path:
            var.set(video_value(path))

    def _on_close(self) -> None:
        if self._dirty():
            answer = messagebox.askyesnocancel("Unsaved changes", "Save your changes before closing?")
            if answer is None or (answer and not self.save()):
                return
        self.root.destroy()


def report_error(kind: type, value: BaseException, tb) -> None:
    """Show an unexpected error in a message box: under pythonw.exe there is no console to print to."""
    messagebox.showerror("Settings", f"Something went wrong: {kind.__name__}: {value}")


def main() -> None:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.report_callback_exception = report_error     # errors in buttons and timers
    try:
        SettingsWindow(root, ROOT / "config.json", ROOT / "samples")
    except (OSError, ValueError) as exc:
        root.withdraw()
        messagebox.showerror("Settings", f"Could not read config.json: {exc}")
        return
    except Exception as exc:
        root.withdraw()
        report_error(type(exc), exc, exc.__traceback__)
        return
    root.mainloop()


if __name__ == "__main__":
    main()
