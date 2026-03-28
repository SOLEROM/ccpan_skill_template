// OPTION F — Multi-Session Tabs
// Manages multiple independent xterm.js instances as tab-switched panels.
// Each tab is independently subscribed to its own tmux session.
//
// HTML needed:
//   <div id="tab-bar"></div>
//   <div id="terminal-mount"></div>   ← xterm instances appended here

// Replace state.terminal / state.currentSession with tab-aware state:
const tabState = {
  sessions:      {},    // sessionId → { term, fitAddon, el }
  activeSession: null,
};

function openTab(sessionId) {
  if (tabState.sessions[sessionId]) {
    activateTab(sessionId);
    return;
  }

  // Create xterm instance
  const term = new Terminal({
    cursorBlink: true, fontSize: 14,
    fontFamily: "'JetBrains Mono',Consolas,monospace",
    scrollback: 5000,
    theme: { background: '#0d1117', foreground: '#e6edf3' },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);

  const el = document.createElement('div');
  el.className = 'tab-terminal';
  el.style.display = 'none';
  document.getElementById('terminal-mount').appendChild(el);

  term.open(el);
  fit.fit();

  term.onData(data => {
    if (tabState.activeSession === sessionId && state.socket?.connected) {
      state.socket.emit('input', { session: sessionId, data });
    }
  });

  tabState.sessions[sessionId] = { term, fitAddon: fit, el };
  activateTab(sessionId);
}

function activateTab(sessionId) {
  // Unsubscribe from current
  if (tabState.activeSession && tabState.activeSession !== sessionId) {
    state.socket.emit('unsubscribe', { session: tabState.activeSession });
  }

  // Hide all, show target
  Object.entries(tabState.sessions).forEach(([sid, s]) => {
    s.el.style.display = sid === sessionId ? 'block' : 'none';
  });

  tabState.activeSession = sessionId;

  const s = tabState.sessions[sessionId];
  s.fitAddon.fit();
  state.socket.emit('subscribe', {
    session: sessionId,
    cols:    s.term.cols,
    rows:    s.term.rows,
  });

  renderTabBar();
}

function closeTab(sessionId) {
  const s = tabState.sessions[sessionId];
  if (!s) return;
  state.socket.emit('unsubscribe', { session: sessionId });
  s.term.dispose();
  s.el.remove();
  delete tabState.sessions[sessionId];
  if (tabState.activeSession === sessionId) {
    tabState.activeSession = null;
    const remaining = Object.keys(tabState.sessions);
    if (remaining.length) activateTab(remaining[0]);
  }
  renderTabBar();
}

function renderTabBar() {
  document.getElementById('tab-bar').innerHTML =
    Object.keys(tabState.sessions).map(sid => `
      <div class="tab ${sid === tabState.activeSession ? 'tab-active' : ''}"
           onclick="activateTab('${esc(sid)}')">
        <span>${esc(sid)}</span>
        <span class="tab-close" onclick="closeTab('${esc(sid)}');event.stopPropagation()">✕</span>
      </div>
    `).join('');
}

// Route output to the correct terminal instance
// Add this to your socket.on('output') handler:
//   if (tabState.sessions[session]) tabState.sessions[session].term.write(data);

// Resize on window change
window.addEventListener('resize', () => {
  const s = tabState.sessions[tabState.activeSession];
  if (!s) return;
  s.fitAddon.fit();
  state.socket.emit('resize', {
    session: tabState.activeSession,
    cols: s.term.cols,
    rows: s.term.rows,
  });
});
