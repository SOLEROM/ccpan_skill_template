# WEBTUI_SKILL — Build a tmux-Backed Web Control Panel

> A comprehensive skill for building browser-accessible command-and-control GUIs using tmux as the session backbone, Flask+SocketIO for the server, and xterm.js for terminal rendering.

---

## 1. Concept & Mental Model

A **WebTUI** app is a web page that feels like a terminal environment. The browser renders a full-featured terminal (xterm.js) connected in real-time to a live tmux session running on the server. The user types, clicks buttons, and watches output—all without SSH access.

```
┌─────────────────────────────────────────────────────┐
│  Browser (xterm.js + optional GUI panels)           │
│                      ↕ WebSocket (Socket.IO)        │
├─────────────────────────────────────────────────────┤
│  Flask Server                                        │
│    ├── TmuxManager  (session lifecycle via CLI)     │
│    ├── PtyBridge    (fork+attach → stream output)   │
│    └── REST routes  (control actions)               │
├─────────────────────────────────────────────────────┤
│  tmux (named sessions, socket-isolated)             │
│    ├── session: prefix-<name>-shell                 │
│    └── session: prefix-<name>-<custom>              │
└─────────────────────────────────────────────────────┘
```

**Key insight:** tmux is the source of truth for terminal state. The web layer is just a multiplexed view into it.

---

## 2. Required Core Stack

Every WebTUI app MUST include these. They are non-negotiable.

### 2.1 Python Dependencies

```
flask>=3.0.0
flask-socketio>=5.3.0
eventlet>=0.33.0          # or gevent>=23.0.0
```

### 2.2 System Dependencies

```bash
# On the server
tmux           # session management
```

### 2.3 Frontend CDN Assets (no build step needed)

```html
<!-- In <head> -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">

<!-- Before </body> -->
<script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
```

---

## 3. Core File Structure

Minimum viable project layout:

```
my-app/
├── server.py                   # Entry point
├── config.json                 # Runtime config (auto-created)
├── modules/
│   ├── tmux_manager.py         # tmux subprocess wrapper
│   ├── pty_bridge.py           # PTY fork+stream
│   ├── routes.py               # REST API
│   └── websocket_handlers.py   # Socket.IO events
├── templates/
│   └── index.html              # SPA shell
└── static/
    └── js/
        └── app.js              # Frontend logic
```

---

## 4. Core Implementation: TmuxManager

Wraps all tmux CLI calls. Uses a custom socket (`-L <socket>`) to isolate sessions from the user's own tmux.

```python
# modules/tmux_manager.py
import subprocess, os

class TmuxManager:
    def __init__(self, socket_name='webtui', prefix='wt-', scrollback=10000):
        self.socket = socket_name
        self.prefix = prefix
        self.scrollback = scrollback
        self.default_cols = 220
        self.default_rows = 50

    def _run(self, *args, timeout=10):
        cmd = ['tmux', '-L', self.socket] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def full_name(self, name):
        return name if name.startswith(self.prefix) else f'{self.prefix}{name}'

    def create_session(self, name, cwd=None, shell_cmd=None):
        """Create a detached tmux session. shell_cmd replaces the login shell."""
        full = self.full_name(name)
        args = ['new-session', '-d', '-s', full,
                '-x', str(self.default_cols), '-y', str(self.default_rows)]
        if cwd and os.path.isdir(cwd):
            args += ['-c', cwd]
        if shell_cmd:
            args += ['--', 'bash', '-c', shell_cmd]
        self._run(*args)
        # Minimal configuration: disable status bar, set history
        self._run('set-option', '-t', full, 'status', 'off')
        self._run('set-option', '-t', full, 'mouse', 'off')
        self._run('set-option', '-t', full, 'history-limit', str(self.scrollback))
        return full

    def session_exists(self, name):
        r = self._run('has-session', '-t', self.full_name(name))
        return r.returncode == 0

    def list_sessions(self):
        r = self._run('list-sessions', '-F', '#{session_name}')
        if r.returncode != 0:
            return []
        return [s for s in r.stdout.strip().split('\n')
                if s and s.startswith(self.prefix)]

    def kill_session(self, name):
        self._run('kill-session', '-t', self.full_name(name))

    def send_keys(self, name, keys):
        self._run('send-keys', '-t', self.full_name(name), keys, timeout=5)

    def send_signal(self, name, sig='SIGINT'):
        """Send SIGINT (Ctrl-C) or other signal to the foreground process."""
        # C-c = ^C = SIGINT equivalent through tmux
        sig_map = {'SIGINT': 'C-c', 'SIGTSTP': 'C-z', 'SIGQUIT': 'C-\\'}
        key = sig_map.get(sig, 'C-c')
        self._run('send-keys', '-t', self.full_name(name), key, timeout=5)

    def resize_window(self, name, cols, rows):
        self._run('resize-window', '-t', self.full_name(name),
                  '-x', str(max(10, cols)), '-y', str(max(3, rows)))

    # Copy-mode scroll (leverages tmux's own scrollback buffer)
    def enter_copy_mode(self, name):
        self._run('copy-mode', '-t', self.full_name(name))

    def exit_copy_mode(self, name):
        self._run('send-keys', '-t', self.full_name(name), 'q', timeout=5)

    def scroll(self, name, direction, lines=3):
        full = self.full_name(name)
        key_map = {
            'up':        f'scroll-up-by {lines}',
            'down':      f'scroll-down-by {lines}',
            'page_up':   'page-up',
            'page_down': 'page-down',
            'top':       'history-top',
            'bottom':    'history-bottom',
        }
        cmd = key_map.get(direction)
        if cmd:
            self._run('command-prompt', '-t', full, f'-I "" "send-keys {cmd}"', timeout=5)
            # Simpler alternative: use send-keys with vi bindings
            vi_map = {
                'up': ['scroll-up'],
                'down': ['scroll-down'],
                'page_up': ['halfpage-up'],
                'page_down': ['halfpage-down'],
            }
            # Use direct copy-mode commands
            self._run('send-keys', '-t', full,
                      'k' * min(lines, 20) if direction == 'up' else
                      'j' * min(lines, 20) if direction == 'down' else
                      '\x02' if direction == 'page_up' else '\x06',
                      timeout=5)
```

---

## 5. Core Implementation: PtyBridge

The PTY bridge is the heart of real-time terminal streaming. It forks a child process that attaches to a tmux session, and the parent reads all output via the master FD, emitting it over WebSocket.

```python
# modules/pty_bridge.py
import os, pty, fcntl, select, threading, struct, termios, re, time
import logging

log = logging.getLogger(__name__)

# Filter dangerous terminal escape sequences that can cause client-side exploits
# or leak terminal state queries through the PTY
_OSC_RE = re.compile(
    rb'\x1b\](?:10|11|12|4;\d+|104|110|111|112|52;[^\x07\x1b]*);[^\x07\x1b]*'
    rb'(?:\x07|\x1b\\)'
)
_DCS_RE = re.compile(rb'\x1bP.*?\x1b\\', re.DOTALL)
_DA_RE  = re.compile(rb'\x1b\[\?[0-9;]*c')  # Device Attributes response

def _filter(data: bytes) -> bytes:
    data = _OSC_RE.sub(b'', data)
    data = _DCS_RE.sub(b'', data)
    data = _DA_RE.sub(b'', data)
    return data


class PtyBridge:
    def __init__(self, tmux_manager, socketio):
        self.tmux = tmux_manager
        self.socketio = socketio
        self.connections = {}      # full_name -> conn dict
        self._lock = threading.Lock()

    def get_or_create(self, name, client_sid, cols=220, rows=50):
        full = self.tmux.full_name(name)
        with self._lock:
            if full not in self.connections:
                master_fd, pid = self._spawn(full, cols, rows)
                reader_thread, stop_event = self._start_reader(full, master_fd)
                self.connections[full] = {
                    'master_fd': master_fd,
                    'pid': pid,
                    'reader': reader_thread,
                    'stop': stop_event,
                    'clients': set(),
                }
            conn = self.connections[full]
            conn['clients'].add(client_sid)
            return conn

    def _spawn(self, full_name, cols, rows):
        self.tmux.resize_window(full_name, cols, rows)
        pid, master_fd = pty.fork()
        if pid == 0:  # child
            os.environ['TERM'] = 'xterm-256color'
            os.execlp('tmux', 'tmux', '-L', self.tmux.socket,
                      'attach', '-t', full_name)
            os._exit(1)
        # parent: make non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._set_winsize(master_fd, rows, cols)
        return master_fd, pid

    def _set_winsize(self, fd, rows, cols):
        winsize = struct.pack('HHHH', rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def _start_reader(self, full_name, master_fd):
        stop_event = threading.Event()

        def reader():
            while not stop_event.is_set():
                try:
                    readable, _, _ = select.select([master_fd], [], [], 0.05)
                    if readable:
                        data = os.read(master_fd, 16384)
                        if data:
                            clean = _filter(data)
                            if clean:
                                self.socketio.emit('output', {
                                    'session': full_name,
                                    'data': clean.decode('utf-8', errors='replace'),
                                }, room=full_name)
                except (OSError, ValueError):
                    break  # FD closed or invalid
            log.debug(f'reader stopped for {full_name}')

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        return t, stop_event

    def send_input(self, name, data: str):
        full = self.tmux.full_name(name)
        conn = self.connections.get(full)
        if conn:
            try:
                os.write(conn['master_fd'], data.encode('utf-8'))
                return True
            except OSError:
                pass
        # Fallback: tmux send-keys (less accurate for special chars)
        self.tmux.send_keys(name, data)
        return False

    def resize(self, name, cols, rows):
        full = self.tmux.full_name(name)
        conn = self.connections.get(full)
        if conn:
            self._set_winsize(conn['master_fd'], rows, cols)
        self.tmux.resize_window(name, cols, rows)

    def remove_client(self, name, sid):
        full = self.tmux.full_name(name)
        conn = self.connections.get(full)
        if not conn:
            return
        conn['clients'].discard(sid)
        if not conn['clients']:
            # Delay cleanup: allow rapid reconnect (e.g., browser refresh)
            def deferred():
                time.sleep(5)
                with self._lock:
                    c = self.connections.get(full)
                    if c and not c['clients']:
                        c['stop'].set()
                        try:
                            os.close(c['master_fd'])
                        except OSError:
                            pass
                        del self.connections[full]
            threading.Thread(target=deferred, daemon=True).start()

    def cleanup_all(self):
        with self._lock:
            for full, conn in list(self.connections.items()):
                conn['stop'].set()
                try:
                    os.close(conn['master_fd'])
                except OSError:
                    pass
            self.connections.clear()
```

---

## 6. Core Implementation: WebSocket Handlers

```python
# modules/websocket_handlers.py
from flask_socketio import emit, join_room, leave_room
from flask import request

def register_websocket_handlers(socketio, app):

    def mgr():
        return app.config['managers']

    @socketio.on('connect')
    def on_connect():
        emit('connected', {'status': 'ok'})

    @socketio.on('disconnect')
    def on_disconnect():
        tmux = mgr()['tmux']
        pty  = mgr()['pty']
        # Remove client from all sessions it was in
        for full_name in list(pty.connections.keys()):
            pty.remove_client(full_name, request.sid)

    @socketio.on('subscribe')
    def on_subscribe(data):
        name = data.get('session', '')
        cols = int(data.get('cols', 220))
        rows = int(data.get('rows', 50))

        tmux = mgr()['tmux']
        pty  = mgr()['pty']

        if not tmux.session_exists(name):
            emit('error', {'message': f'Session {name!r} not found'})
            return

        join_room(tmux.full_name(name))
        pty.get_or_create(name, request.sid, cols, rows)
        emit('subscribed', {'session': tmux.full_name(name)})

    @socketio.on('unsubscribe')
    def on_unsubscribe(data):
        name = data.get('session', '')
        tmux = mgr()['tmux']
        pty  = mgr()['pty']
        leave_room(tmux.full_name(name))
        pty.remove_client(name, request.sid)
        emit('unsubscribed', {'session': tmux.full_name(name)})

    @socketio.on('input')
    def on_input(data):
        name = data.get('session', '')
        keys = data.get('data', '')
        if name and keys:
            mgr()['pty'].send_input(name, keys)

    @socketio.on('resize')
    def on_resize(data):
        name = data.get('session', '')
        cols = int(data.get('cols', 80))
        rows = int(data.get('rows', 24))
        if name:
            mgr()['pty'].resize(name, cols, rows)

    @socketio.on('scroll')
    def on_scroll(data):
        name    = data.get('session', '')
        command = data.get('command', '')  # enter|exit|up|down|page_up|page_down|top|bottom
        lines   = int(data.get('lines', 3))
        tmux    = mgr()['tmux']
        if not name:
            return
        if command == 'enter':
            tmux.enter_copy_mode(name)
        elif command == 'exit':
            tmux.exit_copy_mode(name)
        elif command in ('up', 'down', 'page_up', 'page_down', 'top', 'bottom'):
            tmux.scroll(name, command, lines)

    @socketio.on('signal')
    def on_signal(data):
        name = data.get('session', '')
        sig  = data.get('signal', 'SIGINT')
        if name:
            mgr()['tmux'].send_signal(name, sig)
```

---

## 7. Core Implementation: Flask Server Entry Point

```python
# server.py
import atexit, argparse
from flask import Flask
from flask_socketio import SocketIO
from modules.tmux_manager import TmuxManager
from modules.pty_bridge import PtyBridge
from modules.routes import register_routes
from modules.websocket_handlers import register_websocket_handlers

def create_app(config: dict = None):
    app = Flask(__name__)
    socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

    cfg = config or {}
    tmux = TmuxManager(
        socket_name=cfg.get('tmux_socket', 'webtui'),
        prefix=cfg.get('session_prefix', 'wt-'),
        scrollback=cfg.get('scrollback', 10000),
    )
    pty = PtyBridge(tmux, socketio)

    app.config['managers'] = {'tmux': tmux, 'pty': pty}

    register_routes(app)
    register_websocket_handlers(socketio, app)

    atexit.register(pty.cleanup_all)
    return app, socketio


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--public', action='store_true',
                        help='Bind to 0.0.0.0 (all interfaces)')
    args = parser.parse_args()

    app, socketio = create_app()
    host = '0.0.0.0' if args.public else args.host
    socketio.run(app, host=host, port=args.port, debug=False)
```

---

## 8. Core Implementation: REST Routes

```python
# modules/routes.py
from flask import jsonify, request, render_template

def register_routes(app):

    def mgr():
        return app.config['managers']

    @app.route('/')
    def index():
        return render_template('index.html')

    # --- Session management ---

    @app.route('/api/sessions', methods=['GET'])
    def list_sessions():
        sessions = mgr()['tmux'].list_sessions()
        return jsonify({'sessions': sessions})

    @app.route('/api/sessions', methods=['POST'])
    def create_session():
        data = request.get_json() or {}
        name     = data.get('name', '')
        cwd      = data.get('cwd')
        shell_cmd = data.get('shell_cmd')
        if not name:
            return jsonify({'error': 'name required'}), 400
        full = mgr()['tmux'].create_session(name, cwd=cwd, shell_cmd=shell_cmd)
        return jsonify({'status': 'ok', 'session': full})

    @app.route('/api/sessions/<name>', methods=['DELETE'])
    def kill_session(name):
        mgr()['tmux'].kill_session(name)
        return jsonify({'status': 'ok'})

    @app.route('/api/sessions/<name>/command', methods=['POST'])
    def run_command(name):
        data = request.get_json() or {}
        cmd = data.get('command', '')
        if cmd:
            mgr()['tmux'].send_keys(name, cmd + '\r')
        return jsonify({'status': 'ok'})
```

---

## 9. Core Implementation: Frontend (xterm.js SPA)

### 9.1 HTML Shell (`templates/index.html`)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebTUI Control Panel</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css">
  <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
  <div id="app">
    <header id="header">
      <span id="status-dot" class="dot dot-disconnected"></span>
      <span id="app-title">Control Panel</span>
      <div id="session-tabs"></div>
      <div id="header-actions"></div>
    </header>
    <div id="workspace">
      <aside id="sidebar">
        <div id="session-list"></div>
        <button onclick="createSession()">+ New Session</button>
      </aside>
      <main id="main">
        <div id="toolbar">
          <span id="current-session-name"></span>
          <button onclick="sendSignal('SIGINT')">Ctrl-C</button>
          <button onclick="clearTerminal()">Clear</button>
        </div>
        <div id="terminal-container"></div>
      </main>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js"></script>
  <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
  <script src="/static/js/app.js"></script>
</body>
</html>
```

### 9.2 JavaScript (`static/js/app.js`)

```javascript
// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  socket:         null,
  terminal:       null,
  fitAddon:       null,
  sessions:       [],
  currentSession: null,
  inCopyMode:     false,
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
const esc = s => String(s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');

// ── Terminal initialization ────────────────────────────────────────────────────
function initTerminal() {
  state.terminal = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    fontSize: 14,
    fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
    scrollback: 5000,
    theme: {
      background: '#0d1117', foreground: '#e6edf3',
      cursor: '#e6edf3', cursorAccent: '#0d1117',
      black: '#484f58',   red: '#ff7b72',   green: '#3fb950',  yellow: '#d29922',
      blue:  '#58a6ff',   magenta:'#bc8cff', cyan: '#39c5cf',  white: '#b1bac4',
      brightBlack: '#6e7681', brightRed: '#ffa198', brightGreen: '#56d364',
      brightYellow: '#e3b341', brightBlue: '#79c0ff', brightMagenta: '#d2a8ff',
      brightCyan: '#56d4dd', brightWhite: '#f0f6fc',
    },
  });
  state.fitAddon = new FitAddon.FitAddon();
  state.terminal.loadAddon(state.fitAddon);
  state.terminal.open(document.getElementById('terminal-container'));
  state.fitAddon.fit();

  // Send keyboard input to current session
  state.terminal.onData(data => {
    if (!state.currentSession || !state.socket?.connected) return;
    if (state.inCopyMode) {
      // Exit copy-mode before sending input
      state.socket.emit('scroll', { session: state.currentSession, command: 'exit' });
      state.inCopyMode = false;
      setTimeout(() => state.socket.emit('input', { session: state.currentSession, data }), 20);
    } else {
      state.socket.emit('input', { session: state.currentSession, data });
    }
  });

  // Mouse wheel → tmux copy-mode scrollback
  document.getElementById('terminal-container').addEventListener('wheel', e => {
    e.preventDefault();
    if (!state.currentSession) return;
    const up    = e.deltaY < 0;
    const lines = Math.max(1, Math.round(Math.abs(e.deltaY) / 30));
    if (up && !state.inCopyMode) {
      state.inCopyMode = true;
      state.socket.emit('scroll', { session: state.currentSession, command: 'enter' });
      setTimeout(() =>
        state.socket.emit('scroll', { session: state.currentSession, command: 'up', lines }), 50);
    } else if (state.inCopyMode) {
      state.socket.emit('scroll', {
        session: state.currentSession,
        command: up ? 'up' : 'down',
        lines,
      });
    }
  }, { passive: false });
}

// ── Socket.IO ─────────────────────────────────────────────────────────────────
function initSocket() {
  state.socket = io();

  state.socket.on('connect', () => {
    document.getElementById('status-dot').className = 'dot dot-connected';
    refreshSessions();
  });

  state.socket.on('disconnect', () => {
    document.getElementById('status-dot').className = 'dot dot-disconnected';
  });

  state.socket.on('output', ({ session, data }) => {
    if (session === state.currentSession && state.terminal) {
      state.terminal.write(data);
    }
  });
}

// ── Session management ────────────────────────────────────────────────────────
async function refreshSessions() {
  const res  = await fetch('/api/sessions');
  const data = await res.json();
  state.sessions = data.sessions || [];
  renderSessionList();
}

function renderSessionList() {
  document.getElementById('session-list').innerHTML =
    state.sessions.map(s => `
      <div class="session-item ${s === state.currentSession ? 'active' : ''}"
           onclick="activateSession('${esc(s)}')">
        <span>${esc(s)}</span>
        <button class="btn-kill" onclick="killSession(event,'${esc(s)}')">✕</button>
      </div>
    `).join('');
}

function activateSession(name) {
  if (state.currentSession) {
    state.socket.emit('unsubscribe', { session: state.currentSession });
  }
  state.currentSession = name;
  state.inCopyMode = false;
  state.terminal.clear();
  document.getElementById('current-session-name').textContent = name;
  const { cols, rows } = state.terminal;
  state.socket.emit('subscribe', { session: name, cols, rows });
  renderSessionList();
}

async function createSession() {
  const name = prompt('Session name:');
  if (!name) return;
  await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  await refreshSessions();
  const full = state.sessions.find(s => s.includes(name));
  if (full) activateSession(full);
}

async function killSession(e, name) {
  e.stopPropagation();
  await fetch(`/api/sessions/${encodeURIComponent(name)}`, { method: 'DELETE' });
  if (state.currentSession === name) state.currentSession = null;
  await refreshSessions();
}

function clearTerminal() {
  state.terminal?.clear();
}

function sendSignal(sig) {
  if (!state.currentSession) return;
  state.socket.emit('signal', { session: state.currentSession, signal: sig });
}

// ── Resize ────────────────────────────────────────────────────────────────────
const resizeObserver = new ResizeObserver(() => {
  state.fitAddon?.fit();
  if (state.currentSession && state.socket?.connected) {
    const { cols, rows } = state.terminal;
    state.socket.emit('resize', { session: state.currentSession, cols, rows });
  }
});

// ── Bootstrap ─────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  initSocket();
  initTerminal();
  resizeObserver.observe(document.getElementById('terminal-container'));
});
```

### 9.3 CSS (`static/css/style.css`)

```css
/* Core dark theme variables */
:root {
  --bg-primary:   #0a0c0f;
  --bg-secondary: #0d1117;
  --bg-panel:     #161b22;
  --border:       #30363d;
  --text-primary: #e6edf3;
  --text-muted:   #8b949e;
  --accent:       #58a6ff;
  --success:      #3fb950;
  --danger:       #ff7b72;
  --warning:      #d29922;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  height: 100vh; overflow: hidden; display: flex; flex-direction: column;
}

#app { display: flex; flex-direction: column; height: 100vh; }

#header {
  height: 44px; background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 12px; gap: 12px;
  flex-shrink: 0;
}

#workspace { display: flex; flex: 1; overflow: hidden; }

#sidebar {
  width: 220px; background: var(--bg-panel);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; padding: 8px; gap: 4px;
  overflow-y: auto; flex-shrink: 0;
}

#main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

#toolbar {
  height: 36px; background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 12px; gap: 8px;
}

#terminal-container { flex: 1; padding: 4px; overflow: hidden; }

/* Status dot */
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-connected    { background: var(--success); }
.dot-disconnected { background: var(--danger); }

/* Session items */
.session-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; border-radius: 4px; cursor: pointer;
  border: 1px solid transparent;
}
.session-item:hover { background: var(--bg-secondary); border-color: var(--border); }
.session-item.active { background: var(--bg-secondary); border-color: var(--accent); }

/* Buttons */
button {
  background: var(--bg-secondary); color: var(--text-primary);
  border: 1px solid var(--border); padding: 4px 10px;
  border-radius: 4px; cursor: pointer; font-size: 12px;
}
button:hover { border-color: var(--accent); }

.btn-kill {
  background: transparent; border: none; color: var(--text-muted);
  padding: 2px 4px; cursor: pointer;
}
.btn-kill:hover { color: var(--danger); }
```

---

## 10. Optional Feature Modules

Enable these by adding the corresponding module and wiring it into the server.

---

### OPTION A: Quick Commands (per-session button palette)

Pre-define common commands as clickable buttons per session.

**Add to config:** `commands.json` — map session name → list of `{label, command}`.

**Route additions:**
```python
@app.route('/api/commands/<session>', methods=['GET'])
def get_commands(session):
    cmds = load_json('commands.json').get(session, [])
    return jsonify({'commands': cmds})

@app.route('/api/commands/<session>', methods=['POST'])
def add_command(session):
    data = request.get_json()
    store = load_json('commands.json')
    store.setdefault(session, []).append({'label': data['label'], 'command': data['command']})
    save_json('commands.json', store)
    return jsonify({'status': 'ok'})
```

**Frontend addition:**
```javascript
// Below the toolbar, render a button row:
async function loadCommands(session) {
  const { commands } = await fetch(`/api/commands/${encodeURIComponent(session)}`).then(r => r.json());
  document.getElementById('quick-commands').innerHTML = commands.map((c, i) =>
    `<button onclick="runQuickCommand('${esc(c.command)}')">${esc(c.label)}</button>`
  ).join('');
}
function runQuickCommand(cmd) {
  if (state.currentSession)
    state.socket.emit('input', { session: state.currentSession, data: cmd + '\r' });
}
```

---

### OPTION B: Docker Container Lifecycle Management

Control Docker containers from the web UI.

**Python dependencies:** `docker` Python SDK, or use subprocess with docker CLI.

**New module `modules/docker_manager.py`:**
```python
import subprocess, json

STATES = {'running': 'running', 'exited': 'stopped', 'paused': 'stopped',
          'created': 'stopped', 'dead': 'error'}

def container_status(name):
    r = subprocess.run(['docker', 'inspect', '--format', '{{.State.Status}}', name],
                       capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        return 'unknown'
    raw = r.stdout.strip()
    return STATES.get(raw, 'unknown')

def container_action(name, action):
    """action: start | stop | restart"""
    r = subprocess.run(['docker', action, name], capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stderr.strip()
```

**Routes:**
```python
@app.route('/api/docker/<name>/status')
def docker_status(name):
    return jsonify({'status': container_status(name)})

@app.route('/api/docker/<name>/<action>', methods=['POST'])
def docker_action(name, action):
    if action not in ('start', 'stop', 'restart'):
        return jsonify({'error': 'invalid action'}), 400
    ok, err = container_action(name, action)
    return jsonify({'status': 'ok' if ok else 'error', 'error': err})
```

**Emit status updates via SocketIO after action:**
```python
# In docker_action route, after action completes, emit to all clients:
socketio.emit('container_status', {'name': name, 'status': container_status(name)})
```

**Frontend - Docker control panel per agent:**
```javascript
function renderDockerControls(agent) {
  const { name, status, type } = agent;
  if (type !== 'docker') return '';
  return `
    <div class="docker-controls">
      <span class="status-badge s-${status}">${status}</span>
      ${status !== 'running' ? `<button onclick="dockerAction('${name}','start')">▶ Start</button>` : ''}
      ${status === 'running'  ? `<button onclick="dockerAction('${name}','stop')">■ Stop</button>` : ''}
      ${status === 'running'  ? `<button onclick="dockerAction('${name}','restart')">↺ Restart</button>` : ''}
    </div>`;
}
```

---

### OPTION C: Markdown File Viewer & Editor

Display and edit `.md` files in a side panel, with navigation between linked files.

**Dependencies:** `marked.js` CDN for rendering.

**Server-side (`modules/readme_manager.py`):**
```python
import os, re

MAX_SIZE = 1_000_000  # 1 MB

def safe_resolve(base_dir, rel_path):
    """Resolve relative path, reject traversal, only allow .md files."""
    abs_path = os.path.normpath(os.path.join(base_dir, rel_path))
    if not abs_path.startswith(os.path.abspath(base_dir) + os.sep):
        return None, 'Path traversal rejected'
    if not abs_path.endswith('.md'):
        return None, 'Only .md files allowed'
    return abs_path, None

def read_file(base_dir, rel_path):
    path, err = safe_resolve(base_dir, rel_path)
    if err:
        return None, err
    if not os.path.exists(path):
        return '', None
    with open(path, 'r', encoding='utf-8') as f:
        return f.read(), None

def write_file(base_dir, rel_path, content):
    if len(content.encode('utf-8')) > MAX_SIZE:
        return False, 'Content too large'
    path, err = safe_resolve(base_dir, rel_path)
    if err:
        return False, err
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, path)  # Atomic write
    return True, None
```

**Routes:**
```python
@app.route('/api/files/<path:rel_path>', methods=['GET'])
def read_md(rel_path):
    content, err = read_file(BASE_DIR, rel_path)
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'content': content, 'path': rel_path})

@app.route('/api/files/<path:rel_path>', methods=['POST'])
def write_md(rel_path):
    content = (request.get_json() or {}).get('content', '')
    ok, err = write_file(BASE_DIR, rel_path, content)
    if not ok:
        return jsonify({'error': err}), 400
    return jsonify({'status': 'ok'})
```

**Frontend – Markdown pane:**
```javascript
// Include marked.js: <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>

const mdState = { stack: [], index: -1, editing: false };

async function loadMarkdown(path) {
  const { content } = await fetch(`/api/files/${path}`).then(r => r.json());
  mdState.stack = [{ path, content }];
  mdState.index = 0;
  renderMarkdown();
}

function renderMarkdown() {
  const entry = mdState.stack[mdState.index];
  if (!entry) return;
  const el = document.getElementById('md-view');
  el.innerHTML = marked.parse(entry.content || '*(empty)*');
  // Intercept relative .md links for in-pane navigation
  el.querySelectorAll('a[href]').forEach(a => {
    const href = a.getAttribute('href');
    if (!href || href.startsWith('http') || !href.endsWith('.md')) return;
    a.addEventListener('click', e => {
      e.preventDefault();
      const dir = entry.path.split('/').slice(0, -1).join('/');
      const resolved = resolvePath(dir, href);
      navTo(resolved);
    });
  });
}

function resolvePath(base, rel) {
  return (base ? base + '/' + rel : rel).split('/')
    .reduce((out, p) => {
      if (p === '..' ) out.pop();
      else if (p && p !== '.') out.push(p);
      return out;
    }, []).join('/');
}

async function navTo(path) {
  const { content } = await fetch(`/api/files/${path}`).then(r => r.json());
  mdState.stack = mdState.stack.slice(0, mdState.index + 1);
  mdState.stack.push({ path, content });
  mdState.index++;
  renderMarkdown();
}

async function saveMarkdown() {
  const entry = mdState.stack[mdState.index];
  const content = document.getElementById('md-editor').value;
  await fetch(`/api/files/${entry.path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  });
  entry.content = content;
  mdState.editing = false;
  renderMarkdown();
}
```

---

### OPTION D: X11 GUI Panels (Xvfb + VNC + noVNC)

Display graphical Linux applications in browser panels.

**System dependencies:** `xvfb`, `x11vnc`, `websockify`

**Architecture per panel:**
```
Xvfb :{N} -screen 0 1280x800x24    (virtual framebuffer)
    └─► x11vnc -display :{N} -rfbport {vnc_port}
            └─► websockify {ws_port} localhost:{vnc_port}
                    └─► Browser noVNC client
```

**Module `modules/x11_manager.py`:**
```python
import subprocess, os

class X11Manager:
    # Fixed display assignments (display_num → ports)
    DISPLAYS = {
        100: {'vnc_port': 5900, 'ws_port': 6100},
        101: {'vnc_port': 5901, 'ws_port': 6101},
        102: {'vnc_port': 5902, 'ws_port': 6102},
    }

    def __init__(self):
        self.running = {}  # display_num → {xvfb, vnc, ws, pids}

    def start(self, display_num=100, width=1280, height=800):
        cfg = self.DISPLAYS[display_num]
        display = f':{display_num}'
        procs = {}
        procs['xvfb'] = subprocess.Popen([
            'Xvfb', display, '-screen', '0', f'{width}x{height}x24',
            '-ac', '+extension', 'GLX', '-nolisten', 'tcp'])
        procs['vnc'] = subprocess.Popen([
            'x11vnc', '-display', display, '-rfbport', str(cfg['vnc_port']),
            '-nopw', '-forever', '-shared', '-noxdamage'])
        procs['ws'] = subprocess.Popen([
            'websockify', str(cfg['ws_port']), f"127.0.0.1:{cfg['vnc_port']}"])
        self.running[display_num] = procs
        return cfg

    def stop(self, display_num):
        procs = self.running.pop(display_num, {})
        for p in procs.values():
            try: p.terminate()
            except: pass

    def inject_display_env(self, tmux_manager, session_name, display_num):
        """Set DISPLAY and related env vars in a tmux session."""
        env_vars = {
            'DISPLAY': f':{display_num}',
            'GDK_BACKEND': 'x11',
            'QT_QPA_PLATFORM': 'xcb',
            'LIBGL_ALWAYS_SOFTWARE': '1',
        }
        for k, v in env_vars.items():
            tmux_manager.send_keys(session_name, f'export {k}={v}\r')
```

**Frontend panel (requires noVNC):**
```javascript
// noVNC loaded as ES module:
// <script type="module"> import RFB from '/static/js/novnc/core/rfb.js'; </script>

async function connectGuiPanel(panelIndex) {
  // Start display on-demand
  const res = await fetch('/api/x11/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ panel: panelIndex }),
  });
  const { ws_port } = await res.json();

  const RFB = (await import('/static/js/novnc/core/rfb.js')).default;
  const rfb = new RFB(document.getElementById(`gui-panel-${panelIndex}`),
    `ws://${location.hostname}:${ws_port}`,
    { scaleViewport: true });
}
```

---

### OPTION E: Agent / Service Registry (YAML Config)

Define named services/agents in a `config.yaml` and manage them from the UI.

**`config.yaml` format:**
```yaml
app:
  host: 127.0.0.1
  port: 5000
  tmux_socket: myapp
  session_prefix: "myapp-"
  scrollback_limit: 10000

agents:
  - name: web-server
    type: local_shell          # or: docker
    cwd: /opt/myapp
    auto_start: false
    readme: docs/web.md

  - name: worker
    type: docker
    container: myapp-worker
    cwd: /opt/myapp
    auto_start: false
    readme: docs/worker.md
    tags: [backend, celery]
```

**Registry module (`modules/agent_registry.py`):**
```python
import yaml, os

class Agent:
    VALID_STATUSES = {'configured','starting','running','stopping','stopped','error','unknown'}

    def __init__(self, raw, base_dir):
        self.name      = raw['name']
        self.type      = raw.get('type', 'local_shell')
        self.container = raw.get('container', f'myapp-{self.name}')
        self.cwd       = raw.get('cwd', base_dir)
        self.readme    = raw.get('readme', 'README.md')
        self.tags      = raw.get('tags', [])
        self.status    = 'unknown'

class AgentRegistry:
    def __init__(self, config_path):
        self.config_path = config_path
        self._agents = {}
        self._load()

    def _load(self):
        with open(self.config_path, 'r') as f:
            raw = yaml.safe_load(f)
        base = os.path.dirname(self.config_path)
        self._agents = {a['name']: Agent(a, base) for a in raw.get('agents', [])}

    def all(self): return list(self._agents.values())
    def get(self, name): return self._agents.get(name)
```

---

### OPTION F: Multi-Session Tabs (per-agent sessions)

Show multiple tmux sessions as browser tabs, grouped by agent/context.

**Frontend state:**
```javascript
const state = {
  // ...existing...
  sessions: {},     // sessionId -> { term, fitAddon }
  activeSession: null,
};

function openTab(sessionId) {
  if (state.sessions[sessionId]) { activateTab(sessionId); return; }
  const term = new Terminal({ /* ...options... */ });
  const fit  = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(document.getElementById('terminal-mount'));
  fit.fit();

  term.onData(data => {
    if (state.activeSession === sessionId)
      state.socket.emit('input', { session: sessionId, data });
  });

  state.sessions[sessionId] = { term, fitAddon: fit };
  activateTab(sessionId);
}

function activateTab(sessionId) {
  // Hide all terminals, show this one
  Object.entries(state.sessions).forEach(([sid, s]) => {
    s.term.element?.parentElement?.style.setProperty('display',
      sid === sessionId ? 'block' : 'none');
  });
  if (state.activeSession) {
    state.socket.emit('unsubscribe', { session: state.activeSession });
  }
  state.activeSession = sessionId;
  const { cols, rows } = state.sessions[sessionId].term;
  state.socket.emit('subscribe', { session: sessionId, cols, rows });
  renderTabs();
}
```

---

### OPTION G: Immutable Event Log / Audit Trail

Record all commands and outputs as an append-only JSONL log for auditing or replay.

```python
# modules/event_log.py
import json, threading
from datetime import datetime, timezone

class EventLog:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._seq  = 0

    def append(self, event_type: str, data: dict, user: dict = None):
        with self._lock:
            self._seq += 1
            entry = {
                'seq': self._seq,
                'ts':  datetime.now(timezone.utc).isoformat(),
                'type': event_type,
                'data': data,
            }
            if user:
                entry['user'] = user
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            return entry

    def tail(self, n=100):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            return [json.loads(l) for l in lines[-n:]]
        except FileNotFoundError:
            return []
```

**Common event types:** `session_created`, `session_killed`, `command_sent`, `signal_sent`, `container_started`, `container_stopped`, `file_saved`

---

### OPTION H: SSH Remote Execution

Execute commands on remote hosts via SSH and collect output/artifacts.

**Python dependencies:** `paramiko>=3.4.0`

```python
# modules/ssh_runner.py
import paramiko, threading

class SSHRunner:
    def __init__(self, host, user, key_file=None, password=None, port=22, timeout=30):
        self._cfg = dict(hostname=host, username=user, port=port, timeout=timeout)
        if key_file:
            self._cfg['key_filename'] = key_file
        elif password:
            self._cfg['password'] = password
        self._client = None
        self._lock = threading.Lock()

    def connect(self):
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(**self._cfg)

    def run(self, command, timeout=60):
        with self._lock:
            _, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return exit_code, stdout.read().decode(), stderr.read().decode()

    def get_file(self, remote_path, local_path):
        with self._client.open_sftp() as sftp:
            sftp.get(remote_path, local_path)

    def close(self):
        if self._client:
            self._client.close()
```

---

### OPTION I: Resizable Split Panels

Drag-to-resize between terminal and a side panel (e.g., markdown editor, logs, status).

```html
<!-- HTML structure -->
<div id="workspace">
  <div id="left-panel"><!-- terminal --></div>
  <div id="resize-handle"></div>
  <div id="right-panel"><!-- markdown / status / etc. --></div>
</div>
```

```javascript
function initSplitter() {
  const handle = document.getElementById('resize-handle');
  const left   = document.getElementById('left-panel');
  let dragging = false, startX, startW;

  handle.addEventListener('mousedown', e => {
    dragging = true; startX = e.clientX;
    startW = left.getBoundingClientRect().width;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const total = document.getElementById('workspace').offsetWidth;
    const newW  = Math.min(Math.max(startW + e.clientX - startX, 200), total - 200);
    left.style.width = newW + 'px';
    state.fitAddon?.fit();
  });

  document.addEventListener('mouseup', () => {
    dragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // Emit resize after splitter released
    if (state.currentSession && state.terminal) {
      const { cols, rows } = state.terminal;
      state.socket.emit('resize', { session: state.currentSession, cols, rows });
    }
  });
}
```

```css
#workspace { display: flex; overflow: hidden; }
#left-panel { width: 60%; min-width: 200px; }
#resize-handle {
  width: 6px; cursor: col-resize; background: var(--border);
  flex-shrink: 0; transition: background 0.1s;
}
#resize-handle:hover { background: var(--accent); }
#right-panel { flex: 1; min-width: 200px; overflow-y: auto; }
```

---

### OPTION J: Configuration YAML Editor in UI

Allow live editing of the app's `config.yaml` from the browser.

```python
@app.route('/api/config/yaml', methods=['GET'])
def get_config_yaml():
    with open(CONFIG_PATH, 'r') as f:
        return jsonify({'yaml': f.read()})

@app.route('/api/config/yaml', methods=['POST'])
def save_config_yaml():
    content = (request.get_json() or {}).get('yaml', '')
    try:
        parsed = yaml.safe_load(content)
        if not isinstance(parsed, dict):
            return jsonify({'error': 'Top-level must be a mapping'}), 400
    except yaml.YAMLError as e:
        return jsonify({'error': str(e)}), 400
    tmp = CONFIG_PATH + '.tmp'
    with open(tmp, 'w') as f: f.write(content)
    os.replace(tmp, CONFIG_PATH)
    return jsonify({'status': 'ok'})
```

---

## 11. Security Checklist

Always apply these when exposing the web interface:

| Concern | Mitigation |
|---------|-----------|
| XSS | Escape all user-controlled strings with `esc()` before HTML injection |
| Terminal injection | Filter OSC/DCS escape sequences in PTY output (see Section 5) |
| Path traversal | `normpath` + startswith check before serving any file |
| File size DoS | Reject writes > 1 MB |
| YAML injection | `yaml.safe_load()` only; validate top-level is a dict before saving |
| Open network exposure | Default `--host 127.0.0.1`; use `--public` flag intentionally |
| tmux namespace collision | Use a unique `-L <socket>` name per app instance |
| Session orphans | Deferred cleanup (5s) prevents PTY churn on rapid reconnect |

---

## 12. Naming Conventions

| Concept | Convention | Example |
|---------|-----------|---------|
| tmux socket | `<app-slug>` | `webtui`, `myctl`, `devpanel` |
| session prefix | `<slug>-` | `wt-`, `dev-` |
| session name | `<prefix><agent>-<kind>` | `wt-api-shell`, `dev-worker-exec` |
| REST prefix | `/api/` | `/api/sessions`, `/api/docker/` |
| WebSocket events | `snake_case` | `output`, `subscribe`, `agent_status` |

---

## 13. Recommended `requirements.txt`

```
# Core (always required)
flask>=3.0.0
flask-socketio>=5.3.0
eventlet>=0.33.0

# Option H: SSH execution
paramiko>=3.4.0

# Option E: YAML config
pyyaml>=6.0.1

# Optional: faster JSON
orjson>=3.9.0
```

---

## 14. Quick Start Template

To create a new WebTUI app from scratch:

1. Copy the `Core File Structure` from Section 3
2. Implement `TmuxManager` (Section 4) and `PtyBridge` (Section 5)
3. Wire `WebSocket Handlers` (Section 6) and `Server` (Section 7)
4. Add `REST Routes` (Section 8)
5. Build the HTML shell (Section 9.1), JS (Section 9.2), CSS (Section 9.3)
6. Apply `Security Checklist` (Section 11)
7. Enable any desired **Options** (A–J) from Section 10

The result is a fully functional web control panel with live tmux terminal access, ready to extend with any combination of the optional features.
