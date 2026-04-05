// devmon — Developer Monitor Panel — Frontend

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
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

function el(id) { return document.getElementById(id); }

// ── Terminal initialization ────────────────────────────────────────────────────
function initTerminal() {
  state.terminal = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    fontSize: 14,
    fontFamily: "'JetBrains Mono','Fira Code',Consolas,monospace",
    scrollback: 5000,
    theme: {
      background:      '#0d1117',
      foreground:      '#e6edf3',
      cursor:          '#e6edf3',
      cursorAccent:    '#0d1117',
      black:           '#484f58',
      red:             '#ff7b72',
      green:           '#3fb950',
      yellow:          '#d29922',
      blue:            '#58a6ff',
      magenta:         '#bc8cff',
      cyan:            '#39c5cf',
      white:           '#b1bac4',
      brightBlack:     '#6e7681',
      brightRed:       '#ffa198',
      brightGreen:     '#56d364',
      brightYellow:    '#e3b341',
      brightBlue:      '#79c0ff',
      brightMagenta:   '#d2a8ff',
      brightCyan:      '#56d4dd',
      brightWhite:     '#f0f6fc',
    },
  });

  state.fitAddon = new FitAddon.FitAddon();
  state.terminal.loadAddon(state.fitAddon);
  state.terminal.open(el('terminal-container'));
  state.fitAddon.fit();

  // Send keyboard input to current session
  state.terminal.onData(data => {
    if (!state.currentSession || !state.socket?.connected) return;
    if (state.inCopyMode) {
      state.socket.emit('scroll', { session: state.currentSession, command: 'exit' });
      state.inCopyMode = false;
      setTimeout(() =>
        state.socket.emit('input', { session: state.currentSession, data }), 20);
    } else {
      state.socket.emit('input', { session: state.currentSession, data });
    }
  });

  // Mouse wheel → tmux copy-mode scrollback
  // capture:true + stopPropagation() are REQUIRED: xterm.js attaches its own wheel listener
  // to its internal viewport child element. Without capture phase, xterm consumes the event
  // first and scroll only works with Shift+wheel. Capture fires our handler before xterm's.
  el('terminal-container').addEventListener('wheel', e => {
    e.preventDefault();
    e.stopPropagation();
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
  }, { passive: false, capture: true });
}

// ── Socket.IO ─────────────────────────────────────────────────────────────────
function initSocket() {
  state.socket = io();

  state.socket.on('connect', () => {
    el('status-dot').className = 'dot dot-connected';
    bootstrapSessions().then(() => refreshSessions());
  });

  state.socket.on('disconnect', () => {
    el('status-dot').className = 'dot dot-disconnected';
  });

  state.socket.on('output', ({ session, data }) => {
    if (session === state.currentSession && state.terminal) {
      state.terminal.write(data);
    }
  });

  state.socket.on('error', ({ message }) => {
    console.warn('Server error:', message);
  });
}

// ── Bootstrap: create default sessions ────────────────────────────────────────
async function bootstrapSessions() {
  try {
    await fetch('/api/bootstrap', { method: 'POST' });
  } catch (err) {
    console.warn('Bootstrap failed:', err);
  }
}

// ── Session management ────────────────────────────────────────────────────────
async function refreshSessions() {
  try {
    const res  = await fetch('/api/sessions');
    const data = await res.json();
    state.sessions = data.sessions || [];
    renderSessionTabs();
    // Auto-activate first session if none selected
    if (!state.currentSession && state.sessions.length > 0) {
      activateSession(state.sessions[0]);
    }
    if (state.currentSession) {
      updateRightPanel(state.currentSession);
    }
  } catch (err) {
    console.warn('refreshSessions failed:', err);
  }
}

function renderSessionTabs() {
  el('session-tabs').innerHTML = state.sessions.map(s => `
    <div class="session-tab ${s === state.currentSession ? 'active' : ''}"
         onclick="activateSession('${esc(s)}')">
      <span>${esc(s)}</span>
      <button class="btn-kill" title="Kill session"
              onclick="killSession(event,'${esc(s)}')">✕</button>
    </div>
  `).join('');
}

function activateSession(name) {
  if (state.currentSession === name) return;
  if (state.currentSession) {
    state.socket.emit('unsubscribe', { session: state.currentSession });
  }
  state.currentSession = name;
  state.inCopyMode = false;
  state.terminal.clear();
  el('current-session-name').textContent = name;
  const { cols, rows } = state.terminal;
  state.socket.emit('subscribe', { session: name, cols, rows });
  renderSessionTabs();
  loadQuickCommands(name);
  updateRightPanel(name);
}

async function createSession(name) {
  name = (name || '').trim();
  if (!name) return;
  try {
    await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    await refreshSessions();
    const full = state.sessions.find(s => s.includes(name));
    if (full) activateSession(full);
  } catch (err) {
    console.warn('createSession failed:', err);
  }
}

async function killSession(e, name) {
  e.stopPropagation();
  if (!confirm(`Kill session "${name}"?`)) return;
  try {
    await fetch(`/api/sessions/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (state.currentSession === name) {
      state.currentSession = null;
      state.terminal.clear();
      el('current-session-name').textContent = '';
    }
    await refreshSessions();
  } catch (err) {
    console.warn('killSession failed:', err);
  }
}

function clearTerminal() {
  state.terminal?.clear();
}

function sendSignal(sig) {
  if (!state.currentSession) return;
  state.socket.emit('signal', { session: state.currentSession, signal: sig });
}

// ── Quick Commands (Option A) ─────────────────────────────────────────────────
async function loadQuickCommands(session) {
  const bar = el('quick-commands');
  if (!bar) return;
  try {
    const res  = await fetch(`/api/commands/${encodeURIComponent(session)}`);
    const data = await res.json();
    const cmds = data.commands || [];
    bar.innerHTML = cmds.map((c, i) =>
      `<button class="btn-quick"
               title="${esc(c.command)}"
               onclick="runQuickCommand('${esc(c.command)}')">${esc(c.label)}</button>`
    ).join('');
  } catch (err) {
    console.warn('loadQuickCommands failed:', err);
    bar.innerHTML = '';
  }
}

function runQuickCommand(cmd) {
  if (!state.currentSession || !state.socket?.connected) return;
  // Exit copy-mode first if active
  if (state.inCopyMode) {
    state.socket.emit('scroll', { session: state.currentSession, command: 'exit' });
    state.inCopyMode = false;
  }
  state.socket.emit('input', { session: state.currentSession, data: cmd + '\r' });
}

// ── Right panel — session info + command list ──────────────────────────────────
async function updateRightPanel(session) {
  if (!session) {
    renderRightPanelEmpty();
    return;
  }
  try {
    const [infoRes, cmdsRes] = await Promise.all([
      fetch(`/api/sessions/${encodeURIComponent(session)}/info`),
      fetch(`/api/commands/${encodeURIComponent(session)}`),
    ]);
    const info = await infoRes.json();
    const { commands } = await cmdsRes.json();
    renderRightPanel(info, commands || []);
  } catch (err) {
    console.warn('updateRightPanel failed:', err);
  }
}

function renderRightPanelEmpty() {
  el('right-panel-content').innerHTML = `
    <div class="info-card">
      <div class="info-card-title">No session selected</div>
      <div style="color:var(--text-muted);font-size:12px;">
        Select or create a session to begin.
      </div>
    </div>`;
}

function renderRightPanel(info, commands) {
  const ptyStatus = info.pty_active
    ? `<span class="status-badge ok">active</span>`
    : `<span class="status-badge off">idle</span>`;

  const cmdRows = commands.length > 0
    ? commands.map((c, i) => `
        <div class="cmd-entry">
          <span class="cmd-entry-label"
                onclick="runQuickCommand('${esc(c.command)}')"
                title="Run: ${esc(c.command)}">${esc(c.label)}</span>
          <span class="cmd-entry-snippet">${esc(c.command)}</span>
          <button class="btn-kill" title="Remove command"
                  onclick="removeCommand('${esc(info.session)}',${i})">✕</button>
        </div>`).join('')
    : `<div style="color:var(--text-muted);font-size:12px;">No quick commands defined.</div>`;

  el('right-panel-content').innerHTML = `
    <div class="info-card">
      <div class="info-card-title">Session Info</div>
      <div class="info-row">
        <span class="info-row-label">Name</span>
        <span class="info-row-value">${esc(info.session)}</span>
      </div>
      <div class="info-row">
        <span class="info-row-label">Short</span>
        <span class="info-row-value">${esc(info.short)}</span>
      </div>
      <div class="info-row">
        <span class="info-row-label">tmux</span>
        <span class="info-row-value ${info.exists ? 'active' : 'inactive'}">
          ${info.exists ? 'running' : 'gone'}
        </span>
      </div>
      <div class="info-row">
        <span class="info-row-label">PTY</span>
        <span class="info-row-value">${ptyStatus}</span>
      </div>
      <div class="info-row">
        <span class="info-row-label">Clients</span>
        <span class="info-row-value">${info.client_count}</span>
      </div>
    </div>

    <div>
      <div class="cmd-list-title">Quick Commands</div>
      <div class="cmd-list">${cmdRows}</div>
    </div>

    <div>
      <div class="cmd-list-title">Add Command</div>
      <div id="add-cmd-form" style="display:flex;flex-direction:column;gap:6px;">
        <input id="add-cmd-label" type="text" placeholder="Label (e.g. Disk Usage)"
               style="background:var(--bg-secondary);border:1px solid var(--border);
                      color:var(--text-primary);padding:5px 8px;border-radius:4px;
                      font-family:inherit;font-size:12px;" />
        <input id="add-cmd-command" type="text" placeholder="Command (e.g. df -h)"
               style="background:var(--bg-secondary);border:1px solid var(--border);
                      color:var(--text-primary);padding:5px 8px;border-radius:4px;
                      font-family:inherit;font-size:12px;" />
        <button onclick="addCommand('${esc(info.session)}')"
                style="align-self:flex-start;">+ Add</button>
      </div>
    </div>

    <div style="margin-top:auto;padding-top:8px;border-top:1px solid var(--border);">
      <div class="cmd-list-title">New Session</div>
      <div id="new-session-form" style="display:flex;gap:6px;">
        <input id="new-session-name" type="text" placeholder="Session name"
               style="background:var(--bg-secondary);border:1px solid var(--border);
                      color:var(--text-primary);padding:4px 8px;border-radius:4px;
                      font-family:inherit;font-size:12px;flex:1;"
               onkeydown="if(event.key==='Enter') createNewSession()" />
        <button onclick="createNewSession()">+ New</button>
      </div>
    </div>
  `;

  // Focus fix for inline inputs
  ['add-cmd-label','add-cmd-command','new-session-name'].forEach(id => {
    const inp = el(id);
    if (inp) {
      inp.addEventListener('focus', () => inp.style.borderColor = 'var(--accent)');
      inp.addEventListener('blur',  () => inp.style.borderColor = 'var(--border)');
    }
  });
}

function createNewSession() {
  const inp = el('new-session-name');
  if (!inp) return;
  const name = inp.value.trim();
  if (!name) return;
  inp.value = '';
  createSession(name);
}

async function addCommand(session) {
  const labelEl = el('add-cmd-label');
  const cmdEl   = el('add-cmd-command');
  if (!labelEl || !cmdEl) return;
  const label   = labelEl.value.trim();
  const command = cmdEl.value.trim();
  if (!label || !command) {
    alert('Both label and command are required.');
    return;
  }
  try {
    await fetch(`/api/commands/${encodeURIComponent(session)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, command }),
    });
    labelEl.value = '';
    cmdEl.value   = '';
    // Reload quick commands bar and right panel
    if (state.currentSession) {
      loadQuickCommands(state.currentSession);
      updateRightPanel(state.currentSession);
    }
  } catch (err) {
    console.warn('addCommand failed:', err);
  }
}

async function removeCommand(session, index) {
  try {
    await fetch(`/api/commands/${encodeURIComponent(session)}/${index}`, {
      method: 'DELETE',
    });
    if (state.currentSession) {
      loadQuickCommands(state.currentSession);
      updateRightPanel(state.currentSession);
    }
  } catch (err) {
    console.warn('removeCommand failed:', err);
  }
}

// ── Option I: Resizable split panel ───────────────────────────────────────────
function initSplitter() {
  const handle = el('resize-handle');
  const left   = el('left-panel');
  let dragging = false, startX, startW;

  handle.addEventListener('mousedown', e => {
    dragging = true;
    startX   = e.clientX;
    startW   = left.getBoundingClientRect().width;
    document.body.style.cursor    = 'col-resize';
    document.body.style.userSelect = 'none';
    handle.classList.add('dragging');
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const total = el('workspace').offsetWidth;
    const newW  = Math.min(Math.max(startW + e.clientX - startX, 200), total - 200);
    left.style.width = newW + 'px';
    state.fitAddon?.fit();
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor    = '';
    document.body.style.userSelect = '';
    handle.classList.remove('dragging');
    // Emit resize after splitter released
    if (state.currentSession && state.terminal) {
      const { cols, rows } = state.terminal;
      state.socket.emit('resize', { session: state.currentSession, cols, rows });
    }
  });
}

// ── Resize observer (terminal re-fit when container resizes) ───────────────────
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
  initSplitter();
  resizeObserver.observe(el('terminal-container'));
});
