# WEBTUI_SKILL — tmux-Backed Web Control Panel

> Build browser-accessible command-and-control GUIs: Flask+SocketIO backend, tmux session management, xterm.js terminal in the browser. Code templates live in `scripts/`.

---

## 1. Concept & Mental Model

A **WebTUI** app is a web page that feels like a terminal. The browser renders xterm.js connected in real-time to a live tmux session on the server. Users type, click buttons, and watch output — no SSH needed.

```
┌──────────────────────────────────────────────┐
│  Browser  (xterm.js + optional side panels)  │
│                    ↕ WebSocket (Socket.IO)   │
├──────────────────────────────────────────────┤
│  Flask Server                                │
│    ├── TmuxManager   (session lifecycle)     │
│    ├── PtyBridge     (fork+attach→stream)    │
│    └── REST routes   (control actions)       │
├──────────────────────────────────────────────┤
│  tmux  (named sessions on a custom socket)   │
└──────────────────────────────────────────────┘
```

**Key insight:** tmux owns terminal state. The web layer is a multiplexed view into it — no output is stored server-side beyond tmux's scrollback buffer.

---

## 2. Required Stack

### Python
```
flask>=3.0.0
flask-socketio>=5.3.0
eventlet>=0.33.0
```
See full `requirements.txt` → [`scripts/requirements.txt`](scripts/requirements.txt)

### System
```bash
tmux    # session management (must be on PATH)
```

### Frontend (CDN, no build step)
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
```

---

## 3. Project File Structure

```
my-app/
├── server.py                    # Entry point — create_app() + argparse
├── config.json                  # Runtime config (auto-created)
├── modules/
│   ├── tmux_manager.py          # tmux CLI wrapper
│   ├── pty_bridge.py            # PTY fork + output streaming
│   ├── routes.py                # REST API
│   └── websocket_handlers.py   # Socket.IO event handlers
├── templates/
│   └── index.html               # SPA shell (xterm.js + Socket.IO)
└── static/
    ├── css/style.css
    └── js/app.js
```

---

## 4. Core Components

Copy these files verbatim into every new app. They form the non-negotiable base.

| File | Template | What it does |
|------|----------|--------------|
| `modules/tmux_manager.py` | [`scripts/core/tmux_manager.py`](scripts/core/tmux_manager.py) | Wraps all tmux CLI calls via custom `-L <socket>`. Handles create/kill/list sessions, send-keys, signals, copy-mode scroll, resize. |
| `modules/pty_bridge.py` | [`scripts/core/pty_bridge.py`](scripts/core/pty_bridge.py) | Forks a PTY that `tmux attach`es to a session. Reader thread streams output to SocketIO room. Filters dangerous OSC/DCS/DA escape sequences. Deferred 5s cleanup on disconnect. |
| `modules/websocket_handlers.py` | [`scripts/core/websocket_handlers.py`](scripts/core/websocket_handlers.py) | Registers all Socket.IO events: `connect`, `disconnect`, `subscribe`, `unsubscribe`, `input`, `resize`, `scroll`, `signal`. |
| `modules/routes.py` | [`scripts/core/routes.py`](scripts/core/routes.py) | REST endpoints: `GET/POST /api/sessions`, `DELETE /api/sessions/<name>`, `POST /api/sessions/<name>/command`. |
| `server.py` | [`scripts/core/server.py`](scripts/core/server.py) | `create_app(config)` wires managers. `atexit` cleanup. `--host`, `--port`, `--public` args. |
| `templates/index.html` | [`scripts/core/index.html`](scripts/core/index.html) | HTML shell: header with status dot, sidebar with session list, toolbar, terminal container. |
| `static/js/app.js` | [`scripts/core/app.js`](scripts/core/app.js) | State object, `initTerminal()`, `initSocket()`, session CRUD, mouse-wheel→copy-mode scroll, ResizeObserver. |
| `static/css/style.css` | [`scripts/core/style.css`](scripts/core/style.css) | GitHub-dark theme variables, header/sidebar/toolbar layout, session-item and button styles. |

### Socket.IO Protocol (Core)

**Client → Server**

| Event | Payload | Purpose |
|-------|---------|---------|
| `subscribe` | `{session, cols, rows}` | Attach PTY and start receiving output |
| `unsubscribe` | `{session}` | Detach from session room |
| `input` | `{session, data}` | Send keystrokes to PTY |
| `resize` | `{session, cols, rows}` | Resize PTY + tmux window |
| `scroll` | `{session, command, lines?}` | Drive tmux copy-mode (`enter`\|`exit`\|`up`\|`down`\|`page_up`\|`page_down`\|`top`\|`bottom`) |
| `signal` | `{session, signal}` | Send `SIGINT`/`SIGTSTP` to foreground process |

**Server → Client**

| Event | Payload | Purpose |
|-------|---------|---------|
| `connected` | `{status}` | Handshake confirmation |
| `subscribed` | `{session}` | PTY attached |
| `unsubscribed` | `{session}` | PTY detached |
| `output` | `{session, data}` | Terminal data chunk |
| `error` | `{message}` | Error notification |

### TmuxManager Configuration

```python
TmuxManager(
    socket_name='myapp',    # tmux -L <socket>  — isolates sessions from user's tmux
    prefix='myapp-',        # filters: only sessions starting with this prefix are managed
    scrollback=10000,       # tmux history-limit per session
)
```

### PtyBridge Key Behaviors

- **One PTY per session**, shared by all connected clients (SocketIO room)
- **Non-blocking I/O**: `select()` with 50ms timeout, reads up to 16 KB/chunk
- **Escape filtering**: strips OSC color queries, DCS, DA device-attribute responses (prevent terminal injection)
- **Deferred cleanup**: PTY lives 5 extra seconds after last client disconnects (handles browser refresh)
- **Fallback input**: if PTY write fails, falls back to `tmux send-keys`

---

## 5. Optional Feature Modules

Enable by adding the referenced file and wiring it into `server.py` / `routes.py`.

| Option | File(s) | Extra deps | Description |
|--------|---------|------------|-------------|
| **A — Quick Commands** | [`scripts/options/opt_a_commands.py`](scripts/options/opt_a_commands.py) [`scripts/options/opt_a_commands.js`](scripts/options/opt_a_commands.js) | — | Per-session button palettes saved to `commands.json`. Click to inject command into terminal. |
| **B — Docker Lifecycle** | [`scripts/options/opt_b_docker.py`](scripts/options/opt_b_docker.py) [`scripts/options/opt_b_docker.js`](scripts/options/opt_b_docker.js) | — | Start/stop/restart Docker containers via `docker` CLI. Status via `docker inspect`. Emits `container_status` socket event. |
| **C — Markdown Viewer/Editor** | [`scripts/options/opt_c_markdown.py`](scripts/options/opt_c_markdown.py) [`scripts/options/opt_c_markdown.js`](scripts/options/opt_c_markdown.js) | `marked.js` CDN | Serve/edit `.md` files in a side pane. In-pane relative link navigation with history stack. Path traversal protection. Atomic writes. |
| **D — X11 GUI Panels** | [`scripts/options/opt_d_x11.py`](scripts/options/opt_d_x11.py) [`scripts/options/opt_d_x11.js`](scripts/options/opt_d_x11.js) | `xvfb` `x11vnc` `websockify` noVNC | Virtual X11 displays via Xvfb→x11vnc→websockify→noVNC. Up to 3 panels. On-demand creation. Inject `DISPLAY=:N` into sessions. |
| **E — Agent/Service Registry** | [`scripts/options/opt_e_registry.py`](scripts/options/opt_e_registry.py) [`scripts/options/opt_e_config.yaml`](scripts/options/opt_e_config.yaml) | `pyyaml` | YAML-defined named agents/services (local or docker). Registry with status tracking. |
| **F — Multi-Session Tabs** | [`scripts/options/opt_f_tabs.js`](scripts/options/opt_f_tabs.js) | — | Multiple xterm.js instances as browser tabs. Each tab independently subscribed to its session. Grouped by agent/context. |
| **G — Audit Event Log** | [`scripts/options/opt_g_eventlog.py`](scripts/options/opt_g_eventlog.py) | — | Append-only JSONL log with sequence numbers, timestamps, and optional user attribution. Thread-safe. |
| **H — SSH Remote Execution** | [`scripts/options/opt_h_ssh.py`](scripts/options/opt_h_ssh.py) | `paramiko>=3.4.0` | Run commands on remote hosts. SFTP artifact download. Auto-reconnect with retry. |
| **I — Resizable Split Panel** | [`scripts/options/opt_i_splitter.js`](scripts/options/opt_i_splitter.js) [`scripts/options/opt_i_splitter.css`](scripts/options/opt_i_splitter.css) | — | Drag-to-resize between terminal and a side panel. Triggers `fitAddon.fit()` + resize emit on release. |
| **J — Config YAML Editor** | [`scripts/options/opt_j_config_editor.py`](scripts/options/opt_j_config_editor.py) | `pyyaml` | `GET/POST /api/config/yaml` — serve and save raw YAML with validation. Atomic write via `.tmp` rename. |

---

## 6. Security Checklist

Apply **all of these** before exposing to a network.

| Concern | Rule |
|---------|------|
| XSS | Use `esc()` helper on every user-controlled value injected into HTML |
| Terminal injection | PTY output is filtered for OSC/DCS/DA sequences (built into `pty_bridge.py`) |
| Path traversal | `os.path.normpath` + `startswith(base)` check before reading/writing any file |
| File size DoS | Reject file writes > 1 MB |
| YAML injection | Always `yaml.safe_load()`; validate top-level is `dict` before saving |
| Network exposure | Default `--host 127.0.0.1`; require explicit `--public` for LAN access |
| tmux collision | Use a unique `-L <socket>` per app instance — never share with the user's own tmux |
| PTY orphans | 5-second deferred cleanup prevents churn on browser refresh |

---

## 7. Naming Conventions

| Concept | Pattern | Example |
|---------|---------|---------|
| tmux socket name | `<app-slug>` | `devmon`, `myctl`, `prodpanel` |
| Session prefix | `<slug>-` | `devmon-`, `myctl-` |
| Session full name | `<prefix><context>-<kind>` | `devmon-api-shell`, `myctl-worker-exec` |
| REST namespace | `/api/<resource>` | `/api/sessions`, `/api/docker/` |
| Socket.IO events | `snake_case` | `output`, `subscribe`, `agent_status` |

---

## 8. Quick Start

```bash
# 1. Create project structure
mkdir -p myapp/modules myapp/templates myapp/static/js myapp/static/css

# 2. Copy core templates
cp scripts/core/tmux_manager.py     myapp/modules/
cp scripts/core/pty_bridge.py       myapp/modules/
cp scripts/core/websocket_handlers.py myapp/modules/
cp scripts/core/routes.py           myapp/modules/
cp scripts/core/server.py           myapp/
cp scripts/core/index.html          myapp/templates/
cp scripts/core/app.js              myapp/static/js/
cp scripts/core/style.css           myapp/static/css/
touch myapp/modules/__init__.py

# 3. Edit server.py — change socket_name and prefix
# 4. Install deps and run
pip install flask flask-socketio eventlet
python myapp/server.py --port 5000
```

Add options by copying the relevant `scripts/options/opt_*.py` / `opt_*.js` files and wiring them in.
