// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  socket:         null,
  terminal:       null,
  fitAddon:       null,
  sessions:       [],
  currentSession: null,
  inCopyMode:     false,
};

// ── XSS helper ────────────────────────────────────────────────────────────────
const esc = s => String(s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// ── Terminal ──────────────────────────────────────────────────────────────────
function initTerminal() {
  state.terminal = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    fontSize: 14,
    fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
    scrollback: 5000,
    theme: {
      background: '#0d1117', foreground: '#e6edf3',
      cursor: '#e6edf3',     cursorAccent: '#0d1117',
      black: '#484f58',      red: '#ff7b72',
      green: '#3fb950',      yellow: '#d29922',
      blue:  '#58a6ff',      magenta: '#bc8cff',
      cyan:  '#39c5cf',      white: '#b1bac4',
      brightBlack: '#6e7681',   brightRed: '#ffa198',
      brightGreen: '#56d364',   brightYellow: '#e3b341',
      brightBlue:  '#79c0ff',   brightMagenta: '#d2a8ff',
      brightCyan:  '#56d4dd',   brightWhite: '#f0f6fc',
    },
  });

  state.fitAddon = new FitAddon.FitAddon();
  state.terminal.loadAddon(state.fitAddon);
  state.terminal.open(document.getElementById('terminal-container'));
  state.fitAddon.fit();

  // Keyboard → PTY
  state.terminal.onData(data => {
    if (!state.currentSession || !state.socket?.connected) return;
    if (state.inCopyMode) {
      // Any keystroke exits copy-mode before forwarding
      state.socket.emit('scroll', { session: state.currentSession, command: 'exit' });
      state.inCopyMode = false;
      setTimeout(() =>
        state.socket.emit('input', { session: state.currentSession, data }), 20);
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

// ── Sessions ──────────────────────────────────────────────────────────────────
async function refreshSessions() {
  const data     = await fetch('/api/sessions').then(r => r.json());
  state.sessions = data.sessions || [];
  renderSessionList();
}

function renderSessionList() {
  document.getElementById('session-list').innerHTML =
    state.sessions.map(s => `
      <div class="session-item ${s === state.currentSession ? 'active' : ''}"
           onclick="activateSession('${esc(s)}')">
        <span class="session-name">${esc(s)}</span>
        <button class="btn-kill" onclick="killSession(event,'${esc(s)}')">✕</button>
      </div>
    `).join('') || '<div class="empty-hint">No sessions</div>';
}

function activateSession(name) {
  if (state.currentSession)
    state.socket.emit('unsubscribe', { session: state.currentSession });
  state.currentSession = name;
  state.inCopyMode     = false;
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
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name }),
  });
  await refreshSessions();
  const full = state.sessions.find(s => s.includes(name));
  if (full) activateSession(full);
}

async function killSession(e, name) {
  e.stopPropagation();
  await fetch(`/api/sessions/${encodeURIComponent(name)}`, { method: 'DELETE' });
  if (state.currentSession === name) {
    state.currentSession = null;
    document.getElementById('current-session-name').textContent = '';
  }
  await refreshSessions();
}

function clearTerminal() { state.terminal?.clear(); }

function sendSignal(sig) {
  if (state.currentSession)
    state.socket.emit('signal', { session: state.currentSession, signal: sig });
}

// ── Auto-resize ───────────────────────────────────────────────────────────────
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
