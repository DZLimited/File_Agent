"""
File Manager Agent - Phase 1
-----------------------------
A simple GUI tool that understands typed commands like:

    create folder in E drive in BIS with name CBFEWS
    rename folder E:\\BIS\\CBFEWS_AI to CBFEWS_FINAL
    delete folder E:\\BIS\\OldStuff
    read folder E:\\BIS

and performs the matching action on your real file system.

No API key needed - this uses simple pattern matching (regex), not an LLM.
Works on Windows. Run with: python file_agent.py
"""

import os
import re
import shutil
import tkinter as tk
from tkinter import scrolledtext, messagebox


# ----------------------------------------------------------------------
# CORE FILE ACTIONS  (the "hands" - these actually touch your disk)
# ----------------------------------------------------------------------

def create_folder(path: str) -> str:
    if os.path.exists(path):
        return f"Folder already exists: {path}"
    os.makedirs(path)
    return f"Created folder: {path}"


def rename_folder(old_path: str, new_path: str) -> str:
    if not os.path.exists(old_path):
        return f"Folder not found: {old_path}"
    if os.path.exists(new_path):
        return f"A folder already exists at: {new_path}"
    os.rename(old_path, new_path)
    return f"Renamed:\n  {old_path}\n  -> {new_path}"


def delete_folder(path: str) -> str:
    if not os.path.exists(path):
        return f"Folder not found: {path}"
    shutil.rmtree(path)
    return f"Deleted folder: {path}"


def read_folder(path: str) -> str:
    if not os.path.exists(path):
        return f"Folder not found: {path}"
    items = os.listdir(path)
    if not items:
        return f"{path} is empty."
    lines = [f"Contents of {path}:"]
    for item in items:
        full = os.path.join(path, item)
        tag = "[DIR]" if os.path.isdir(full) else "[FILE]"
        lines.append(f"  {tag} {item}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# COMMAND PARSER  (the "brain" - turns your sentence into an action)
# ----------------------------------------------------------------------

def build_path(drive: str, subfolder: str, name: str, suffix: str) -> str:
    """
    Builds something like: E:\\BIS\\CBFEWS_AI
    drive     -> "E"
    subfolder -> "BIS"   (may be empty)
    name      -> "CBFEWS"
    suffix    -> "_AI"   (auto-appended if set in the Settings box)
    """
    full_name = f"{name}{suffix}" if suffix else name
    parts = [f"{drive.upper()}:\\"]
    if subfolder:
        parts.append(subfolder)
    parts.append(full_name)
    return os.path.join(*parts)


def parse_command(text: str, default_suffix: str):
    """
    Returns (action_description, result_string)
    Understands 4 intents: create, rename, delete, read
    """
    t = text.strip().lower()

    # ---------- CREATE ----------
    # e.g. "create folder in E drive in BIS with name of CBFEWS"
    #      "make a folder in E: in BIS named CBFEWS"
    if re.search(r"\b(create|make)\b.*\bfolder\b", t):
        drive_match = re.search(r"\b([a-z])\s*(?:drive|:)\b", t)
        subfolder_match = re.search(r"\bin\s+([a-zA-Z0-9_\- ]+?)(?:\s+with\b|\s+named\b|\s+name\b|$)", t)
        name_match = re.search(r"\b(?:name(?:d)?\s+(?:of\s+)?|called\s+)([a-zA-Z0-9_\-]+)", t)

        if not drive_match or not name_match:
            return "create", ("Couldn't understand the drive or the name.\n"
                               "Try: create folder in E drive in BIS with name CBFEWS")

        drive = drive_match.group(1)
        name = name_match.group(1).upper()

        # figure out the subfolder: take the 'in X' phrase that is NOT the drive itself
        subfolder = ""
        in_matches = re.findall(r"\bin\s+([a-zA-Z0-9_\- ]+?)(?=\s+in\b|\s+with\b|\s+named\b|\s+name\b|$)", t)
        for m in in_matches:
            m_clean = m.strip()
            if m_clean and not re.fullmatch(rf"{drive}\s*(drive)?", m_clean):
                subfolder = m_clean.upper().replace(" ", "")
                break

        path = build_path(drive, subfolder, name, default_suffix)
        return "create", create_folder(path)

    # ---------- RENAME ----------
    # e.g. "rename folder E:\BIS\CBFEWS_AI to CBFEWS_FINAL"
    if "rename" in t:
        m = re.search(r"rename\s+folder\s+(.+?)\s+to\s+(.+)", text.strip(), re.IGNORECASE)
        if not m:
            return "rename", "Try: rename folder <full path> to <new name or full path>"
        old_path = m.group(1).strip()
        new_val = m.group(2).strip()
        # if they only gave a new name (not a full path), keep it in the same parent dir
        if os.path.dirname(new_val) == "":
            new_path = os.path.join(os.path.dirname(old_path), new_val)
        else:
            new_path = new_val
        return "rename", rename_folder(old_path, new_path)

    # ---------- DELETE ----------
    # e.g. "delete folder E:\BIS\OldStuff"
    if re.search(r"\b(delete|remove)\b.*\bfolder\b", t):
        m = re.search(r"(?:delete|remove)\s+folder\s+(.+)", text.strip(), re.IGNORECASE)
        if not m:
            return "delete", "Try: delete folder <full path>"
        path = m.group(1).strip()
        return "delete", ("__CONFIRM_DELETE__", path)

    # ---------- READ / LIST ----------
    # e.g. "read folder E:\BIS"  /  "list folder E:\BIS"  /  "show folder E:\BIS"
    if re.search(r"\b(read|list|show)\b.*\bfolder\b", t):
        m = re.search(r"(?:read|list|show)\s+folder\s+(.+)", text.strip(), re.IGNORECASE)
        if not m:
            return "read", "Try: read folder <full path>"
        path = m.group(1).strip()
        return "read", read_folder(path)

    return "unknown", ("Didn't recognize that command. Try one of:\n"
                        "  create folder in E drive in BIS with name CBFEWS\n"
                        "  rename folder <path> to <new name>\n"
                        "  delete folder <path>\n"
                        "  read folder <path>")


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------

class FileAgentApp:
    def __init__(self, root):
        self.root = root
        root.title("File Manager Agent")
        root.geometry("640x520")
        root.configure(bg="#1e1e1e")

        FG = "#e6e6e6"
        BG = "#1e1e1e"
        ENTRY_BG = "#2b2b2b"
        ACCENT = "#4da3ff"

        title = tk.Label(root, text="File Manager Agent", bg=BG, fg=FG,
                          font=("Segoe UI", 16, "bold"))
        title.pack(pady=(14, 2))

        subtitle = tk.Label(root, text="Type a command below (create / rename / delete / read a folder)",
                             bg=BG, fg="#9a9a9a", font=("Segoe UI", 9))
        subtitle.pack(pady=(0, 10))

        # --- Settings row: auto-suffix ---
        settings_frame = tk.Frame(root, bg=BG)
        settings_frame.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(settings_frame, text="Auto-suffix for new folder names (optional):",
                  bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self.suffix_var = tk.StringVar(value="_AI")
        suffix_entry = tk.Entry(settings_frame, textvariable=self.suffix_var, width=10,
                                 bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat")
        suffix_entry.pack(side="left", padx=8)
        tk.Label(settings_frame, text='(so "CBFEWS" becomes "CBFEWS_AI")',
                  bg=BG, fg="#9a9a9a", font=("Segoe UI", 8, "italic")).pack(side="left")

        # --- Command entry ---
        entry_frame = tk.Frame(root, bg=BG)
        entry_frame.pack(fill="x", padx=16, pady=(4, 8))

        self.command_var = tk.StringVar()
        self.entry = tk.Entry(entry_frame, textvariable=self.command_var,
                               font=("Segoe UI", 11), bg=ENTRY_BG, fg=FG,
                               insertbackground=FG, relief="flat")
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.run_command())

        run_btn = tk.Button(entry_frame, text="Run", command=self.run_command,
                             bg=ACCENT, fg="white", relief="flat", font=("Segoe UI", 10, "bold"),
                             padx=16, activebackground="#3a8ee0")
        run_btn.pack(side="right")

        # --- Quick example buttons ---
        examples_frame = tk.Frame(root, bg=BG)
        examples_frame.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(examples_frame, text="Examples:", bg=BG, fg="#9a9a9a",
                  font=("Segoe UI", 8)).pack(anchor="w")
        examples = [
            "create folder in E drive in BIS with name CBFEWS",
            "read folder E:\\BIS",
        ]
        for ex in examples:
            b = tk.Button(examples_frame, text=ex, bg="#2b2b2b", fg="#9a9a9a",
                           relief="flat", font=("Segoe UI", 8),
                           command=lambda x=ex: self.command_var.set(x))
            b.pack(anchor="w", pady=1)

        # --- Log / output ---
        self.log = scrolledtext.ScrolledText(root, bg="#111111", fg="#7CFC7C",
                                              font=("Consolas", 10), relief="flat",
                                              wrap="word")
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log.insert("end", "Ready. Type a command above and press Run.\n\n")
        self.log.configure(state="disabled")

        self._pending_delete_path = None  # holds path awaiting confirmation

    def print_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run_command(self):
        text = self.command_var.get().strip()
        if not text:
            return
        suffix = self.suffix_var.get().strip()
        self.print_log(f"> {text}")

        action, result = parse_command(text, suffix)

        # Special case: delete needs a confirmation popup before it actually runs
        if action == "delete" and isinstance(result, tuple) and result[0] == "__CONFIRM_DELETE__":
            path = result[1]
            confirmed = messagebox.askyesno(
                "Confirm delete",
                f"Are you sure you want to permanently delete this folder?\n\n{path}"
            )
            if confirmed:
                outcome = delete_folder(path)
            else:
                outcome = "Delete cancelled."
            self.print_log(outcome)
        else:
            self.print_log(result)

        self.command_var.set("")


if __name__ == "__main__":
    root = tk.Tk()
    app = FileAgentApp(root)
    root.mainloop()
