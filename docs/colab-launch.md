# Launching ToM-PE from Google Colab

This document describes the content of a Google Colab notebook that lets a
non-technical user launch the ToM-PE interfaces from a browser, **without
installing anything locally**. Every dependency — Python packages, the API
server, the Streamlit and Gradio apps, and the tunneling tool used to expose
them publicly — is installed inside the Colab runtime.

The notebook supports launching either interface, independently or together:

- **Teacher dashboard** — Streamlit, exposed via `localtunnel` (the
  Streamlit framework has no built-in public-sharing option).
- **Student app** — Gradio, exposed via Gradio's built-in `share=True`
  tunnel (no extra tooling needed).

Each section below corresponds to **one cell** in the notebook. The cell type
is shown in brackets: `[Markdown]` for explanatory cells, `[Code]` for
executable cells.

---

## Part A — Common setup (always run)

### Cell 1 — [Markdown] — Welcome

```markdown
# ToM-PE — Colab launcher

This notebook starts the ToM-PE platform and gives you a public URL you can
open (or share with students) in any browser. You don't need to install
anything on your own computer.

**What you'll need before starting**
- A Google account (you already have one — that's how you opened Colab)
- At least one LLM API key:
  - **OpenAI** (recommended — used for error injection and as an MT backend), or
  - **Anthropic** (Claude — used as an MT backend)
- *(Optional)* A **Google Translate** API key for Google MT

**How to use the notebook**
1. Run **Part A — Common setup** (cells 2–5).  *Required.*
2. Then run **Part B** to launch the *teacher dashboard*, **Part C** to launch
   the *student app*, or both.
3. Each launcher cell prints a public URL — click it to open the interface.

> ⚠️ Colab sessions are temporary. When you close this tab or the runtime
> disconnects (after ~90 min idle), everything stops and data created during
> the session is lost. See *Part D — Persist data to Google Drive* to keep
> data across sessions.
```

---

### Cell 2 — [Code] — Clone the repository

```python
!git clone --depth 1 https://github.com/diana-nurbakova/tompe.git
%cd tompe
```

*Notes:* `--depth 1` skips git history; `%cd` is a Colab magic that changes
the working directory for all subsequent cells.

---

### Cell 3 — [Code] — Install everything (Python + Node tunneling tool)

```python
# 1. Python dependencies (FastAPI, Streamlit, Gradio, Pydantic, OpenAI/Anthropic SDKs, …)
!pip install -q -e .

# 2. localtunnel — exposes the Streamlit port over the public internet.
#    Colab has Node.js preinstalled, so `npm` is already available.
!npm install -g localtunnel >/dev/null 2>&1

# 3. Sanity check
import shutil, importlib
assert shutil.which("streamlit"), "streamlit CLI missing"
assert shutil.which("lt"),        "localtunnel CLI missing"
for mod in ("gradio", "fastapi", "tompe"):
    importlib.import_module(mod)
print("All dependencies installed.")
```

Takes ~1–2 minutes the first time. Nothing else needs to be installed
locally — the whole environment lives inside this Colab runtime.

---

### Cell 4 — [Code] — Provide your API keys

```python
import os
from getpass import getpass
from pathlib import Path

def _ask(label: str, env_key: str) -> str:
    val = getpass(f"{label} (press Enter to skip): ").strip()
    if val:
        os.environ[env_key] = val
    return val

openai_key    = _ask("OpenAI API key",           "OPENAI_API_KEY")
anthropic_key = _ask("Anthropic API key",        "ANTHROPIC_API_KEY")
google_key    = _ask("Google Translate API key", "GOOGLE_TRANSLATE_API_KEY")

# Persist to .env so subprocess-launched apps pick the keys up.
lines = []
if openai_key:    lines.append(f"OPENAI_API_KEY={openai_key}")
if anthropic_key: lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")
if google_key:    lines.append(f"GOOGLE_TRANSLATE_API_KEY={google_key}")
Path(".env").write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"\nConfigured {len(lines)} key(s).")
```

*Why `getpass` and not a Colab form field:* form values are saved inside the
notebook file and would leak when the notebook is shared. `getpass` reads
from a masked input and never writes the value to disk (only into the
process environment and the `.env` file, which is gitignored).

---

### Cell 5 — [Code] — *(Optional)* Download a small corpus sample

```python
# Skip this cell if you only want to demo the interface with no source segments.
!python scripts/ingest_corpus.py --corpus europarl --max-segments 500
```

A 500-segment Europarl sample is enough to try the corpus browser, MT
generation, and error injection flows. Increase `--max-segments` or run the
script for other corpora (`dgt_tm`, `eurlex`, `unpc`) when preparing real
exercises.

---

## Part B — Launch the teacher dashboard (Streamlit)

> Run cells 6 and 7 to start the Streamlit teacher interface and get a
> public URL. Skip this part if you only need the student app.

### Cell 6 — [Code] — Start Streamlit in the background

```python
import subprocess, time, pathlib

LOG = pathlib.Path("streamlit.log")
streamlit_proc = subprocess.Popen(
    [
        "streamlit", "run", "src/tompe/interfaces/teacher_app.py",
        "--server.port", "8501",
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--browser.gatherUsageStats", "false",
    ],
    stdout=LOG.open("w"),
    stderr=subprocess.STDOUT,
)

for _ in range(30):
    time.sleep(1)
    if "You can now view your Streamlit app" in LOG.read_text(errors="ignore"):
        print("Streamlit is up on port 8501.")
        break
else:
    print("Streamlit did not start in 30s — open streamlit.log in the file panel.")
```

`server.headless=true` stops Streamlit from trying to open a browser inside
Colab. The log file is written to `streamlit.log` so you can inspect it if
something goes wrong.

---

### Cell 7 — [Code] — Open the public tunnel (teacher URL)

```python
import subprocess, re

# The localtunnel "reminder" page asks for a tunnel password = the runtime's public IP.
ip = subprocess.check_output(["curl", "-s", "https://loca.lt/mytunnelpassword"]).decode().strip()
print(f"Tunnel password (paste this when the localtunnel page asks): {ip}\n")

tunnel = subprocess.Popen(
    ["lt", "--port", "8501"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)

for line in tunnel.stdout:
    print(line, end="")
    m = re.search(r"https://[a-z0-9\-]+\.loca\.lt", line)
    if m:
        print(f"\n👉 Teacher dashboard: {m.group(0)}")
        break
```

When the URL is opened for the first time, localtunnel shows a one-time
*"reminder"* page asking for the tunnel password — that's the IP printed
above. After clicking *Continue*, the Streamlit dashboard appears.

**Keep this cell running for the whole session** — closing it tears down
the tunnel.

---

## Part C — Launch the student app (Gradio)

> Run cell 8 to start the Gradio student app and get a public URL you can
> share with students. This part is independent from Part B — you can run
> just the student app, just the teacher dashboard, or both at the same
> time.

### Cell 8 — [Code] — Start the student app with Gradio's built-in share tunnel

```python
import os, subprocess, pathlib, re, time

# Gradio has built-in public sharing — no localtunnel needed.
# We override the app's launch call by setting GRADIO_SHARE=true and binding to 0.0.0.0.
os.environ["GRADIO_SERVER_NAME"] = "0.0.0.0"
os.environ["GRADIO_SERVER_PORT"] = "7860"
os.environ["GRADIO_SHARE"]       = "true"

STUDENT_LOG = pathlib.Path("student.log")
student_proc = subprocess.Popen(
    ["python", "-m", "tompe.interfaces.student_app"],
    stdout=STUDENT_LOG.open("w"),
    stderr=subprocess.STDOUT,
    env=os.environ.copy(),
)

# Wait for Gradio to print the public *.gradio.live URL.
public_url = None
for _ in range(60):
    time.sleep(1)
    text = STUDENT_LOG.read_text(errors="ignore")
    m = re.search(r"https://[a-z0-9\-]+\.gradio\.live", text)
    if m:
        public_url = m.group(0)
        break

if public_url:
    print(f"👉 Student app: {public_url}")
else:
    print("Gradio did not return a public URL in 60s — open student.log in the file panel.")
```

*Note:* the student app reads exercises and items from the platform's data
store, which is populated by the teacher dashboard. For a realistic demo
session, run **Part A → Part B** first (and create at least one exercise
through the teacher dashboard), then run **Part C** to give students a way in.

If the student app's code does not currently honor `GRADIO_SHARE` /
`GRADIO_SERVER_NAME` env vars (some versions of Gradio require these to be
passed to `.launch()` directly), this cell may need a small edit in
`student_app.py`'s `main()` to read those env vars — flag this when
converting the markdown to a real notebook.

---

## Part D — Optional extras

### Cell 9 — [Code] — *(Optional)* Persist data to Google Drive

```python
from google.colab import drive
import pathlib, shutil

drive.mount("/content/drive")

DRIVE_DATA = pathlib.Path("/content/drive/MyDrive/tompe-data")
DRIVE_DATA.mkdir(parents=True, exist_ok=True)

# Symlink the project's data/ dir to Drive so items, classes, and responses survive.
local_data = pathlib.Path("/content/tompe/data")
if local_data.exists() and not local_data.is_symlink():
    shutil.rmtree(local_data)
if not local_data.exists():
    local_data.symlink_to(DRIVE_DATA)

print(f"data/ → {DRIVE_DATA}")
```

Run this **before Cell 6 / Cell 8** so the symlink is in place when the
apps read/write data.

---

### Cell 10 — [Code] — *(Optional)* Use ngrok instead of localtunnel

```python
!pip install -q pyngrok
from pyngrok import ngrok

# Paste a free token from https://dashboard.ngrok.com/get-started/your-authtoken
ngrok.set_auth_token("YOUR_NGROK_TOKEN")
print("Teacher dashboard URL:", ngrok.connect(8501).public_url)
```

Use this if localtunnel is blocked on your network or if you prefer a more
stable URL across runtime restarts (with an ngrok account).

---

### Cell 11 — [Markdown] — Stopping & troubleshooting

```markdown
## Stopping

- **All processes**: *Runtime → Disconnect and delete runtime* — kills
  Streamlit, Gradio, and the tunnel.
- **Just one**: interrupt the corresponding launcher cell (the ⏹ button).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `localtunnel` URL shows "Tunnel Unavailable" | The Streamlit process exited. Open `streamlit.log` in the file panel (left sidebar) and read the last lines. |
| No `*.gradio.live` URL appears within 60s | Open `student.log` in the file panel. The most common cause is missing API keys (re-run Cell 4). |
| `MissingAPIKey` errors inside an interface | The `.env` file wasn't written. Re-run Cell 4. |
| Teacher dashboard loads but corpus is empty | Run Cell 5 (corpus download). |
| Students see "exercise not found" | Create at least one exercise through the teacher dashboard before sharing the student URL. |
| `npm install` fails | Restart the runtime (*Runtime → Restart runtime*) and re-run Cell 3. Colab occasionally ships without a working npm in fresh runtimes. |
```

---

## Summary — cell list

Cells in the order they appear in the notebook:

| # | Type | Purpose |
| - | --- | --- |
| 1 | Markdown | Welcome / instructions |
| **Part A — Common setup** | | |
| 2 | Code | Clone repo |
| 3 | Code | Install Python deps + `localtunnel` (Node) |
| 4 | Code | Enter API keys (masked) → `.env` |
| 5 | Code | *(Optional)* Download a 500-segment corpus sample |
| **Part B — Teacher dashboard** | | |
| 6 | Code | Start Streamlit in background |
| 7 | Code | Open localtunnel → print public URL |
| **Part C — Student app** | | |
| 8 | Code | Start Gradio student app with `share=true` → print public URL |
| **Part D — Optional** | | |
| 9 | Code | Persist `data/` to Google Drive |
| 10 | Code | Use ngrok instead of localtunnel |
| 11 | Markdown | Stopping & troubleshooting |

Once this markdown is reviewed, each `[Code]` block becomes one code cell
and each `[Markdown]` block becomes one markdown cell in
`notebooks/colab_launch.ipynb`, with an *"Open in Colab"* badge added to
the README.
