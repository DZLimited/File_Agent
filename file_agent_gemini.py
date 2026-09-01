"""
File Manager Agent - Phase 3 (Gemini-powered understanding)
--------------------------------------------------------------
A GUI tool that understands typed OR spoken commands like:

    create folder in E drive in BIS with name CBFEWS
    create a folder on desktop with the name of ABC
    rename folder E:\\BIS\\CBFEWS_AI to CBFEWS_FINAL
    delete folder E:\\BIS\\OldStuff
    read folder E:\\BIS

and performs the matching action on your real file system.

TWO "BRAINS", AUTOMATIC FALLBACK:
  1. If you've entered a free Google Gemini API key, commands are understood
     by Gemini (handles messy/natural phrasing, typos, voice mishears, etc).
  2. If no key is set, or the Gemini call fails (no internet, rate limit,
     etc), it automatically falls back to the built-in rule-based parser
     from Phase 1/2, so the app never fully breaks.

Voice input uses the free SpeechRecognition library - no key needed for that.

FIRST-TIME SETUP (run once in Command Prompt):
    pip install SpeechRecognition pyaudio google-genai

    If "pip install pyaudio" fails on Windows, instead run:
        pip install pipwin
        pipwin install pyaudio

GET A FREE GEMINI API KEY:
    1. Go to https://aistudio.google.com/app/apikey
    2. Sign in with a Google account, click "Create API key"
    3. Paste it into the app's "Gemini API Key" box and click Save
       (it's saved locally in gemini_key.txt next to this script - never
       uploaded anywhere by this app)

Works on Windows. Run with: python file_agent.py
"""

import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

try:
    import speech_recognition as sr
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KEY_FILE = os.path.join(SCRIPT_DIR, "gemini_key.txt")


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


def dispatch(name: str, args: dict) -> str:
    """Runs the actual file action once we know which one + its arguments."""
    if name == "create_folder":
        return create_folder(args["path"])
    if name == "rename_folder":
        return rename_folder(args["old_path"], args["new_path"])
    if name == "read_folder":
        return read_folder(args["path"])
    return f"Unrecognized action: {name}"


# ----------------------------------------------------------------------
# KNOWN WINDOWS LOCATIONS
# ----------------------------------------------------------------------

KNOWN_LOCATIONS = {
    "desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
    "documents": os.path.join(os.path.expanduser("~"), "Documents"),
    "downloads": os.path.join(os.path.expanduser("~"), "Downloads"),
    "pictures": os.path.join(os.path.expanduser("~"), "Pictures"),
    "videos": os.path.join(os.path.expanduser("~"), "Videos"),
    "music": os.path.join(os.path.expanduser("~"), "Music"),
}


# ----------------------------------------------------------------------
# BRAIN #1: RULE-BASED PARSER (no API needed - always available)
# Returns (ok, name_or_message, args)
#   ok=True  -> name_or_message is the action name, args is its arguments
#   ok=False -> name_or_message is an error/help message, args is None
# ----------------------------------------------------------------------

def parse_with_rules(text: str, default_suffix: str):
    t = text.strip().lower()

    # ---------- CREATE ----------
    if re.search(r"\b(create|make)\b.*\bfolder\b", t):
        name_match = re.search(r"\b(?:name(?:d)?\s+(?:of\s+)?|called\s+)([a-zA-Z0-9_\-]+)", t)
        if not name_match:
            return False, ("Couldn't find a folder name in that.\n"
                            "Try: create folder on desktop with name ABC\n"
                            "  or: create folder in E drive in BIS with name CBFEWS"), None
        name = name_match.group(1).upper()

        location_phrases = re.findall(
            r"\b(?:in|on)\s+([a-zA-Z0-9_\- ]+?)(?=\s+in\b|\s+on\b|\s+with\b|\s+named\b|\s+name\b|$)", t
        )
        location_phrases = [p.strip() for p in location_phrases if p.strip()]

        base_path = None
        remaining_subfolders = []

        for phrase in location_phrases:
            if phrase in KNOWN_LOCATIONS and base_path is None:
                base_path = KNOWN_LOCATIONS[phrase]
                continue
            drive_in_phrase = re.fullmatch(r"([a-z])\s*(?:drive)?", phrase)
            if drive_in_phrase and base_path is None:
                base_path = f"{drive_in_phrase.group(1).upper()}:\\"
                continue
            remaining_subfolders.append(phrase.upper().replace(" ", ""))

        if base_path is None:
            return False, ("Couldn't tell where to put it. Say a drive (e.g. \"E drive\") "
                            "or a known location (Desktop, Documents, Downloads, Pictures, "
                            "Videos, Music).\n"
                            "Try: create folder on desktop with name ABC"), None

        full_name = f"{name}{default_suffix}" if default_suffix else name
        path = os.path.join(base_path, *remaining_subfolders, full_name)
        return True, "create_folder", {"path": path}

    # ---------- RENAME ----------
    if "rename" in t:
        m = re.search(r"rename\s+folder\s+(.+?)\s+to\s+(.+)", text.strip(), re.IGNORECASE)
        if not m:
            return False, "Try: rename folder <full path> to <new name or full path>", None
        old_path = m.group(1).strip()
        new_val = m.group(2).strip()
        if os.path.dirname(new_val) == "":
            new_path = os.path.join(os.path.dirname(old_path), new_val)
        else:
            new_path = new_val
        return True, "rename_folder", {"old_path": old_path, "new_path": new_path}

    # ---------- DELETE ----------
    if re.search(r"\b(delete|remove)\b.*\bfolder\b", t):
        m = re.search(r"(?:delete|remove)\s+folder\s+(.+)", text.strip(), re.IGNORECASE)
        if not m:
            return False, "Try: delete folder <full path>", None
        return True, "delete_folder", {"path": m.group(1).strip()}

    # ---------- READ / LIST ----------
    if re.search(r"\b(read|list|show)\b.*\bfolder\b", t):
        m = re.search(r"(?:read|list|show)\s+folder\s+(.+)", text.strip(), re.IGNORECASE)
        if not m:
            return False, "Try: read folder <full path>", None
        return True, "read_folder", {"path": m.group(1).strip()}

    return False, ("Didn't recognize that command. Try one of:\n"
                    "  create folder in E drive in BIS with name CBFEWS\n"
                    "  rename folder <path> to <new name>\n"
                    "  delete folder <path>\n"
                    "  read folder <path>"), None


# ----------------------------------------------------------------------
# BRAIN #2: GEMINI PARSER (needs a free API key + internet)
# ----------------------------------------------------------------------

GEMINI_FUNCTIONS = [
    {
        "name": "create_folder",
        "description": "Create a new folder at an absolute Windows path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                          "description": "Full absolute folder path, e.g. E:\\BIS\\CBFEWS_AI"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "rename_folder",
        "description": "Rename or move an existing folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "old_path": {"type": "string", "description": "Full absolute path of the existing folder"},
                "new_path": {"type": "string", "description": "Full absolute path to rename/move it to"},
            },
            "required": ["old_path", "new_path"],
        },
    },
    {
        "name": "delete_folder",
        "description": "Permanently delete an existing folder and everything inside it.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full absolute path of the folder to delete"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "read_folder",
        "description": "List the contents of an existing folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full absolute path of the folder to read"}
            },
            "required": ["path"],
        },
    },
]


def _build_gemini_tool():
    declarations = [
        genai_types.FunctionDeclaration(
            name=f["name"],
            description=f["description"],
            parameters_json_schema=f["parameters"],
        )
        for f in GEMINI_FUNCTIONS
    ]
    return genai_types.Tool(function_declarations=declarations)


def build_system_prompt(default_suffix: str) -> str:
    locations_text = "\n".join(f"  - {name}: {path}" for name, path in KNOWN_LOCATIONS.items())
    if default_suffix:
        suffix_text = (f'When the user asks to CREATE a new folder, append the suffix "{default_suffix}" '
                        f'to the name they said, unless they explicitly say not to add a suffix.')
    else:
        suffix_text = "Use the exact folder name the user says, with no suffix added."

    return f"""You are a file-system command interpreter for a Windows PC.
Your only job is to call exactly one of the provided functions (create_folder, rename_folder,
delete_folder, read_folder) that matches what the user asked for, using full absolute Windows paths.

Known special folders on this PC (use these exact paths whenever the user mentions them by name):
{locations_text}

For drive letters (e.g. "E drive", "E:"), build paths like E:\\SubFolder\\Name.

{suffix_text}

Always build one complete, absolute path (e.g. E:\\BIS\\CBFEWS_AI or {KNOWN_LOCATIONS['desktop']}\\ABC).
Voice-to-text input may contain small transcription errors (e.g. misheard project codenames) -
use context and common sense to infer the intended word.
If the request is genuinely ambiguous or missing required info, do not call a function -
just reply in plain text asking a short clarifying question instead."""


def parse_with_gemini(text: str, default_suffix: str, api_key: str):
    """
    Returns (ok, name_or_message, args) in the same shape as parse_with_rules.
    Raises an exception on network/API failures so the caller can fall back.
    """
    client = genai.Client(api_key=api_key)
    tool = _build_gemini_tool()
    config = genai_types.GenerateContentConfig(
        system_instruction=build_system_prompt(default_suffix),
        tools=[tool],
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=text,
        config=config,
    )

    if response.function_calls:
        fc = response.function_calls[0]
        args = dict(fc.args)
        return True, fc.name, args

    # Gemini replied in plain text instead of calling a function
    # (usually means it needs clarification)
    return False, (response.text or "Gemini couldn't determine an action from that."), None


# ----------------------------------------------------------------------
# API KEY STORAGE (plain local text file next to the script)
# ----------------------------------------------------------------------

def load_api_key() -> str:
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_api_key(key: str):
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key.strip())


# ----------------------------------------------------------------------
# GUI
# ----------------------------------------------------------------------

class FileAgentApp:
    def __init__(self, root):
        self.root = root
        root.title("File Manager Agent")
        root.geometry("680x640")
        root.configure(bg="#1e1e1e")

        FG = "#e6e6e6"
        BG = "#1e1e1e"
        ENTRY_BG = "#2b2b2b"
        ACCENT = "#4da3ff"
        self.FG, self.BG, self.ENTRY_BG, self.ACCENT = FG, BG, ENTRY_BG, ACCENT

        title = tk.Label(root, text="File Manager Agent", bg=BG, fg=FG,
                          font=("Segoe UI", 16, "bold"))
        title.pack(pady=(14, 2))

        subtitle = tk.Label(root, text="Type or speak a command (create / rename / delete / read a folder)",
                             bg=BG, fg="#9a9a9a", font=("Segoe UI", 9))
        subtitle.pack(pady=(0, 10))

        # --- Gemini API key row ---
        key_frame = tk.Frame(root, bg=BG)
        key_frame.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(key_frame, text="Gemini API Key:", bg=BG, fg=FG, font=("Segoe UI", 9)).pack(side="left")
        self.api_key = load_api_key()
        self.api_key_var = tk.StringVar(value=self.api_key)
        key_entry = tk.Entry(key_frame, textvariable=self.api_key_var, show="*", width=30,
                              bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat")
        key_entry.pack(side="left", padx=8, ipady=3)
        save_key_btn = tk.Button(key_frame, text="Save", command=self.save_key,
                                  bg="#2b2b2b", fg=FG, relief="flat", font=("Segoe UI", 9),
                                  activebackground="#3a3a3a")
        save_key_btn.pack(side="left")

        self.ai_enabled_var = tk.BooleanVar(value=bool(self.api_key) and GEMINI_AVAILABLE)
        ai_check = tk.Checkbutton(key_frame, text="Use Gemini AI for understanding commands",
                                   variable=self.ai_enabled_var, bg=BG, fg=FG,
                                   selectcolor="#2b2b2b", activebackground=BG,
                                   activeforeground=FG, font=("Segoe UI", 9))
        ai_check.pack(side="left", padx=(12, 0))

        if not GEMINI_AVAILABLE:
            ai_check.configure(state="disabled")
            self.print_log_ready_note = "google-genai not installed - run: pip install google-genai"

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

        self.mic_btn = tk.Button(entry_frame, text="\U0001F3A4 Speak", command=self.start_listening,
                                  bg="#2b2b2b", fg=FG, relief="flat", font=("Segoe UI", 10, "bold"),
                                  padx=12, activebackground="#3a3a3a")
        self.mic_btn.pack(side="right", padx=(0, 8))

        # --- Voice status / auto-run toggle ---
        voice_row = tk.Frame(root, bg=BG)
        voice_row.pack(fill="x", padx=16, pady=(0, 4))
        self.voice_status = tk.Label(voice_row, text="", bg=BG, fg="#4da3ff", font=("Segoe UI", 9, "italic"))
        self.voice_status.pack(side="left")

        self.auto_run_var = tk.BooleanVar(value=True)
        auto_run_check = tk.Checkbutton(voice_row, text="Run automatically after speaking",
                                         variable=self.auto_run_var, bg=BG, fg=FG,
                                         selectcolor="#2b2b2b", activebackground=BG,
                                         activeforeground=FG, font=("Segoe UI", 9))
        auto_run_check.pack(side="right")

        if not VOICE_AVAILABLE:
            self.mic_btn.configure(state="disabled")
            self.voice_status.configure(
                text="Voice libraries not installed - run: pip install SpeechRecognition pyaudio",
                fg="#e07b7b"
            )

        # --- Quick example buttons ---
        examples_frame = tk.Frame(root, bg=BG)
        examples_frame.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(examples_frame, text="Examples:", bg=BG, fg="#9a9a9a",
                  font=("Segoe UI", 8)).pack(anchor="w")
        examples = [
            "create folder in E drive in BIS with name CBFEWS",
            "create a folder on desktop called ABC",
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
        self.log.insert("end", "Ready. Type or speak a command above.\n")
        if not self.api_key:
            self.log.insert("end", "No Gemini key set yet - using built-in rule-based parsing "
                                    "(still works fine for structured commands).\n")
        self.log.insert("end", "\n")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------------
    # SETTINGS
    # ------------------------------------------------------------------

    def save_key(self):
        key = self.api_key_var.get().strip()
        save_api_key(key)
        self.api_key = key
        if key and GEMINI_AVAILABLE:
            self.ai_enabled_var.set(True)
            self.print_log("Gemini API key saved. AI-powered understanding is now ON.")
        elif not GEMINI_AVAILABLE:
            self.print_log("Key saved, but google-genai isn't installed yet - "
                            "run: pip install google-genai")
        else:
            self.ai_enabled_var.set(False)
            self.print_log("Key cleared. Using built-in rule-based parsing.")

    # ------------------------------------------------------------------
    # VOICE
    # ------------------------------------------------------------------

    def start_listening(self):
        if not VOICE_AVAILABLE:
            return
        self.mic_btn.configure(state="disabled", text="Listening...")
        self.voice_status.configure(text="Listening... speak your command now.", fg="#4da3ff")
        thread = threading.Thread(target=self._listen_worker, daemon=True)
        thread.start()

    def _listen_worker(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(source, timeout=6, phrase_time_limit=8)
            text = recognizer.recognize_google(audio)
            self.root.after(0, self._on_voice_result, text, None)
        except sr.WaitTimeoutError:
            self.root.after(0, self._on_voice_result, None, "No speech detected - try again.")
        except sr.UnknownValueError:
            self.root.after(0, self._on_voice_result, None, "Couldn't understand the audio - try again.")
        except sr.RequestError as e:
            self.root.after(0, self._on_voice_result, None, f"Speech service error: {e}")
        except OSError as e:
            self.root.after(0, self._on_voice_result, None, f"Microphone error: {e}")

    def _on_voice_result(self, text, error):
        self.mic_btn.configure(state="normal", text="\U0001F3A4 Speak")
        if error:
            self.voice_status.configure(text=error, fg="#e07b7b")
            return
        self.voice_status.configure(text=f'Heard: "{text}"', fg="#7CFC7C")
        self.command_var.set(text)
        if self.auto_run_var.get():
            self.run_command()

    # ------------------------------------------------------------------
    # COMMAND EXECUTION
    # ------------------------------------------------------------------

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

        use_ai = self.ai_enabled_var.get() and GEMINI_AVAILABLE and self.api_key
        source = "rules"

        if use_ai:
            try:
                ok, name_or_msg, args = parse_with_gemini(text, suffix, self.api_key)
                source = "Gemini"
            except Exception as e:
                self.print_log(f"[Gemini unavailable ({e}) - falling back to rule-based parsing]")
                ok, name_or_msg, args = parse_with_rules(text, suffix)
                source = "rules (fallback)"
        else:
            ok, name_or_msg, args = parse_with_rules(text, suffix)

        if not ok:
            self.print_log(name_or_msg)
            self.command_var.set("")
            return

        action_name = name_or_msg

        if action_name == "delete_folder":
            path = args["path"]
            confirmed = messagebox.askyesno(
                "Confirm delete",
                f"Are you sure you want to permanently delete this folder?\n\n{path}"
            )
            outcome = delete_folder(path) if confirmed else "Delete cancelled."
        else:
            outcome = dispatch(action_name, args)

        self.print_log(f"[{source}] {outcome}")
        self.command_var.set("")


if __name__ == "__main__":
    root = tk.Tk()
    app = FileAgentApp(root)
    root.mainloop()
