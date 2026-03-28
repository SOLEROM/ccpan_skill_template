# webTui

A collection of reference implementations and a reusable skill for building **tmux-backed web control panels** — browser GUIs that give you a live terminal, command palettes, Docker controls, and more, without SSH access.

---

## What's in this repo

```
webTui/
├── WEBTUI_SKILL.md        ← The skill document (start here)
├── scripts/               ← Copy-paste templates referenced by the skill
│   ├── core/              ← Required base files for every new app
│   └── options/           ← Optional feature modules (A–J)
└── test/
    └── devmon/            ← Demo app built from the skill
```

---

## The Skill: `WEBTUI_SKILL.md`

The skill is a concise guide (~200 lines) that explains the full pattern and points to ready-to-use code in `scripts/`.

**Read the skill when you want to:**
- Understand the architecture before building
- Know which options to enable for a given use case
- Check the security checklist before deploying

**Use the scripts directly when you want to:**
- Copy-paste code into a new project without reading everything

---

## Quick Start — New App in 5 Minutes

```bash
# 1. Create project
mkdir myapp
cd myapp
mkdir -p modules templates static/js static/css

# 2. Copy core templates
cp ../scripts/core/tmux_manager.py       modules/
cp ../scripts/core/pty_bridge.py         modules/
cp ../scripts/core/websocket_handlers.py modules/
cp ../scripts/core/routes.py             modules/
cp ../scripts/core/server.py             .
cp ../scripts/core/index.html            templates/
cp ../scripts/core/app.js                static/js/
cp ../scripts/core/style.css             static/css/
touch modules/__init__.py

# 3. Customise server.py — change tmux_socket and prefix
#    e.g.: socket_name='myapp', prefix='myapp-'

# 4. Install and run
pip install flask flask-socketio eventlet
python server.py
# Open http://127.0.0.1:5000
```

---

## Core Architecture

```
Browser  (xterm.js + Socket.IO)
    ↕  WebSocket
Flask + SocketIO
    ├── TmuxManager      manage named tmux sessions via -L <socket>
    ├── PtyBridge        fork PTY, attach tmux, stream output to browser
    └── REST /api/       create/kill sessions, send commands
```

**Key principle:** tmux is the source of truth. The browser is just a view. Sessions survive page refreshes and reconnects because they live in tmux.

---

## Optional Feature Modules

Enable any of these by copying the corresponding file from `scripts/options/` and wiring it in.

| Option | Files | What it adds |
|--------|-------|--------------|
| **A** | `opt_a_commands.py` + `.js` | Per-session quick command button palette |
| **B** | `opt_b_docker.py` + `.js` | Docker start/stop/restart + live status |
| **C** | `opt_c_markdown.py` + `.js` | In-pane `.md` viewer/editor with link navigation |
| **D** | `opt_d_x11.py` + `.js` | X11 GUI panels via Xvfb → x11vnc → noVNC |
| **E** | `opt_e_registry.py` + `opt_e_config.yaml` | YAML-defined agent/service registry |
| **F** | `opt_f_tabs.js` | Multiple xterm.js sessions as browser tabs |
| **G** | `opt_g_eventlog.py` | Append-only JSONL audit trail |
| **H** | `opt_h_ssh.py` | SSH remote execution + SFTP file transfer |
| **I** | `opt_i_splitter.js` + `.css` | Drag-to-resize terminal / side panel split |
| **J** | `opt_j_config_editor.py` | Live YAML config editor in the browser |

---

## Demo App

`test/devmon/` is a working **Developer Monitor Panel** built from the skill using Core + Options A and I.

```bash
cd test/devmon
pip install -r requirements.txt
python server.py
# Open http://127.0.0.1:5000
```

It auto-creates three sessions (`devmon-logs`, `devmon-shell`, `devmon-build`) on first connect, with pre-seeded quick commands (disk usage, memory, process list) and a resizable split layout.

---

## Security Notes

Always apply before exposing on a network:

- Default bind is `127.0.0.1` — use `--public` explicitly for LAN
- PTY output is filtered for OSC/DCS/DA escape sequences (built into `pty_bridge.py`)
- Use `yaml.safe_load()` everywhere — never `yaml.load()`
- Validate file paths with `normpath` + `startswith` before reads/writes
- Use the XSS `esc()` helper on all user-controlled HTML injections
