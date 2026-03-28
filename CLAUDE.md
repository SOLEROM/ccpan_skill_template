# CLAUDE.md — webTui Project Context

This file tells Claude Code everything needed to continue working on this project in future sessions.

---

## What This Project Is

A **skill library** for building tmux-backed web control panels. The owner builds custom command-and-control web GUIs regularly and wanted a reusable pattern so future Claude sessions can scaffold new apps without re-deriving the architecture.

The deliverable is not a running app — it is a skill document + code templates that future Claude agents can use to build new apps quickly and correctly.

---

## Repository Layout

```
webTui/
├── CLAUDE.md              ← this file
├── README.md              ← human-facing intro + quick start
├── WEBTUI_SKILL.md        ← the skill document (primary artifact, ~200 lines)
├── scripts/
│   ├── core/              ← 8 files, copy verbatim into every new app
│   │   ├── tmux_manager.py
│   │   ├── pty_bridge.py
│   │   ├── websocket_handlers.py
│   │   ├── routes.py
│   │   ├── server.py
│   │   ├── index.html
│   │   ├── app.js
│   │   └── style.css
│   ├── options/           ← 16 files, one per optional feature (A–J)
│   │   ├── opt_a_commands.{py,js}     quick command button palettes
│   │   ├── opt_b_docker.{py,js}       docker container lifecycle
│   │   ├── opt_c_markdown.{py,js}     .md viewer/editor in side pane
│   │   ├── opt_d_x11.{py,js}          X11/VNC GUI panels via noVNC
│   │   ├── opt_e_registry.py + .yaml  YAML agent/service registry
│   │   ├── opt_f_tabs.js              multi-session tab switching
│   │   ├── opt_g_eventlog.py          append-only JSONL audit log
│   │   ├── opt_h_ssh.py               SSH remote execution + SFTP
│   │   ├── opt_i_splitter.{js,css}    drag-to-resize split panel
│   │   └── opt_j_config_editor.py     live YAML config editor in UI
│   └── requirements.txt
└── test/
    └── devmon/            ← demo app (Core + Options A + I), Python syntax verified
```

---

## The Three Reference Implementations (What We Learned)

These three projects were studied to extract the common pattern and are now deleted. The knowledge below is the distilled output — read this instead of looking for the folders.

### ref1 — ECR (Experiment Control & Record)
**Does NOT use tmux.** SSH/subprocess execution. Notable unique features:
- YAML profile-driven command definitions with parameter templating `{var}`
- SSH remote execution via paramiko (run commands on a remote device)
- Automatic SFTP artifact download after command completion
- Append-only JSONL event timeline with sequence numbers and user attribution
- Background collectors (periodic monitoring threads)
- Run lifecycle: create → start → pause → resume → complete
- HTML and ZIP export of full experiment record
- Multi-user collaboration via SocketIO rooms

**Lesson:** ref1 showed us what a fully audit-trailed, SSH-remote workflow looks like. Its patterns are encoded in Options G (event log) and H (SSH).

### ref2 — WebTui (Tmux Control Panel)
**Core tmux+PTY implementation.** The most technically detailed reference. Notable features:
- Custom tmux socket (`-L <socket>`) for namespace isolation per browser tab
- PTY fork + reader thread → SocketIO output streaming (the pattern we copied verbatim)
- OSC/DCS/DA escape sequence filtering in PTY output (security)
- xterm.js with GitHub-dark theme, FitAddon, mouse-wheel copy-mode scroll
- X11 GUI panels: Xvfb → x11vnc → websockify → noVNC in browser (up to 3 panels)
- 4 layout modes: terminal-only, split-1/2/3 GUI panels
- Detachable floating GUI panels with drag-to-reposition
- Per-tab socket/prefix config so different browser tabs manage different tmux namespaces
- Quick command palette per session

**Lesson:** ref2 gave us the canonical PTY bridge implementation. The escape sequence filter regex in `pty_bridge.py` was taken directly from here. The X11 panel pattern is in Option D.

### ref3 — Claude Control Plane
**Most feature-complete.** Docker + tmux + markdown editing. Notable features:
- Docker container lifecycle (start/stop/restart/status via `docker inspect`)
- Parallel docker status refresh via `ThreadPoolExecutor`
- YAML-defined agent registry with status tracking
- `shell_cmd` parameter in tmux session creation — makes the session's direct process be `docker exec -it <container> bash` instead of a host shell, so exit drops cleanly
- Markdown viewer with in-pane relative link navigation (history stack with back/forward)
- Path traversal protection for file serving (`normpath` + `startswith`)
- Atomic file writes (`.tmp` then `os.replace()`)
- Optimistic UI: update status badge immediately before the API call resolves
- Session auto-restore on WebSocket reconnect (saves selected agent to localStorage)
- Auto-open a shell when a docker container reaches `running` state

**Lesson:** ref3 gave us the Docker pattern (Option B), markdown editor (Option C), agent registry (Option E), and the `shell_cmd` trick for clean docker sessions.

---

## The Core Pattern (Non-Negotiable in Every App)

### Python stack
```
flask + flask-socketio + eventlet
```
Always `async_mode='eventlet'`. Never threading mode for production — it can't handle concurrent WebSocket connections cleanly.

### TmuxManager
- Wraps all `tmux -L <socket>` CLI calls via `subprocess.run`
- Custom socket isolates the app's sessions from the user's own tmux
- Session prefix (e.g. `myapp-`) filters `list-sessions` to only managed sessions
- Always configure sessions: `status off`, `mouse off`, `history-limit N`
- `shell_cmd` param in `create_session` is important for docker exec sessions — prevents "drop to host shell" when the inner process exits

### PtyBridge
- `pty.fork()` → child executes `tmux attach -t <session>` → parent holds master FD
- Reader thread uses `select()` with 50ms timeout, reads 16 KB chunks
- Output filtered through three regex patterns before emitting to browser
- One PTY per session shared by all browser clients (SocketIO room)
- 5-second deferred cleanup on disconnect (handles browser refresh without creating a new PTY)
- Fallback: if `os.write(master_fd)` fails, use `tmux send-keys`

### Escape sequence filter (copy exactly)
```python
_OSC_RE = re.compile(
    rb'\x1b\](?:10|11|12|4;\d+|104|110|111|112|52;[^\x07\x1b]*);[^\x07\x1b]*'
    rb'(?:\x07|\x1b\\)'
)
_DCS_RE = re.compile(rb'\x1bP.*?\x1b\\', re.DOTALL)
_DA_RE  = re.compile(rb'\x1b\[\?[0-9;]*c')
```
These filter color queries, clipboard operations, and device-attribute responses that can be exploited or cause client-side display issues.

### Frontend (xterm.js)
- CDN only — no npm/webpack. Three `<script>` tags: xterm, xterm-addon-fit, socket.io
- Mouse wheel scroll pattern: enter tmux copy-mode on first wheel-up, exit on any keypress
- `ResizeObserver` on `#terminal-container` → `fitAddon.fit()` + emit `resize`
- XSS: always pass user-controlled strings through `esc()` before HTML injection

### WebSocket protocol
```
subscribe   {session, cols, rows}  → attach PTY, join room
unsubscribe {session}              → leave room, deferred PTY cleanup
input       {session, data}        → write to PTY master FD
resize      {session, cols, rows}  → TIOCSWINSZ + tmux resize-window
scroll      {session, command, lines?} → copy-mode navigation
signal      {session, signal}      → C-c / C-z via tmux send-keys
output      {session, data}        → server→browser terminal data
```

---

## Key Decisions Made During This Session

### Why WEBTUI_SKILL.md + scripts/ instead of one big file
The original `WEBTUI_SKILL.md` was ~1,490 lines of mixed prose + code. Too long for a future Claude session to hold in context efficiently. We split it:
- Skill = pure prose: architecture, tables, decisions, checklists (~200 lines)
- Scripts = actual code: ready to copy verbatim, no extraction needed

Future pattern: skill files describe *what and why*, scripts contain *how* as actual runnable code.

### Why tmux (not raw PTY or subprocess)
- Sessions survive server restarts if tmux socket stays alive
- Multiple browser clients can view the same session (shared PTY room)
- Built-in scrollback buffer means we don't store output server-side
- Copy-mode gives history scrolling without any client-side buffering

### Why custom socket (`-L <socket>`)
- Isolates managed sessions from the user's personal tmux
- Multiple WebTUI apps on same server each get their own namespace
- `list-sessions` filtered by prefix is reliable — no collision risk

### Why eventlet not threading
- `flask-socketio` with `threading` mode serializes concurrent requests
- `eventlet` patches stdlib for async I/O — handles many concurrent WebSocket connections correctly

### Why deferred 5-second PTY cleanup
- Browser refresh triggers disconnect+reconnect in rapid succession
- Without the delay, a refresh destroys the PTY and creates a new one, losing terminal state
- 5 seconds is enough for any normal reconnect; adjust if needed

### Atomic file writes everywhere
```python
tmp = path + '.tmp'
with open(tmp, 'w') as f: f.write(content)
os.replace(tmp, path)   # atomic on POSIX
```
Never write directly to the target path — a crash mid-write produces a corrupt file.

---

## Security Rules (Never Skip These)

| What | Rule |
|------|------|
| HTML injection | `esc()` on every user-controlled value |
| Terminal output | OSC/DCS/DA filter in `pty_bridge.py` — already there, don't remove |
| File serving | `normpath` + `startswith(base_dir)` before any read/write |
| File writes | Reject > 1 MB, `.md` files only where appropriate |
| YAML | `yaml.safe_load()` only, validate result is `dict` before saving |
| Network | Default `127.0.0.1`, explicit `--public` flag for LAN |
| tmux | Unique `-L <socket>` per app — never share with user's own tmux |

---

## How to Build a New App Using This Skill

1. Read `WEBTUI_SKILL.md` — especially the options table to decide what to enable
2. Copy core scripts to new project (8 files + `__init__.py`)
3. Edit `server.py` — change `socket_name` and `prefix` to match the app name
4. Copy any option files needed (`opt_a_commands.py`, etc.)
5. Wire options: add `register_*_routes(app)` calls in `server.py` or `routes.py`
6. Edit `index.html` — add any option-specific HTML elements noted in JS file comments
7. Run `python server.py` — verify a session can be created and typed into
8. Deploy with `--public` only if network access is needed

---

## Testing Approach Used

A subagent was given only `WEBTUI_SKILL.md` and asked to build `test/devmon/` from scratch. We then verified:
- All Python files parse without syntax errors (`python -c "import ast; ast.parse(...)"`)
- File structure matches the expected layout
- Correct module imports (no missing dependencies)

This "cold-read test" validates the skill is self-contained enough for a fresh Claude session to use without additional context. If the skill changes significantly, re-run this test.

---

## Owner Preferences (Learned During Session)

- Prefers **minimal, no-build-step frontend** — CDN only, vanilla JS, no React/Vue/webpack
- Prefers **Python + Flask** for the server (not Node/Express)
- Wants **optional features clearly separated** so they can be cherry-picked per project
- Skill files should be **concise prose + references**, not inline code dumps
- Code templates should be **complete and runnable**, not skeleton stubs with TODOs
- Dark terminal aesthetic: GitHub-dark color palette (`#0d1117` background, `#e6edf3` foreground, `#58a6ff` accent)

---

## What NOT to Do

- Do not look for `ref1/`, `ref2/`, `ref3/` — those folders have been deleted; all knowledge from them is captured in the "Three Reference Implementations" section above
- Do not add build steps (npm, webpack, etc.) to frontend code — CDN only
- Do not change `async_mode` from `eventlet` — threading mode breaks concurrent WebSocket
- Do not use `yaml.load()` — always `yaml.safe_load()`
- Do not write to files directly — always use the `.tmp` → `os.replace()` pattern
- Do not share a tmux socket between two different apps running on the same server
