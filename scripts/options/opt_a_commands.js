// OPTION A — Quick Commands frontend
// Add a command palette below the toolbar. Buttons inject commands into the terminal.
//
// HTML needed:
//   <div id="quick-commands"></div>   ← place below #toolbar
//   <!-- Add-command form (optional) -->
//   <input id="cmd-label" placeholder="Label">
//   <input id="cmd-value" placeholder="Command">
//   <button onclick="addQuickCommand()">Add</button>

async function loadQuickCommands(session) {
  if (!session) {
    document.getElementById('quick-commands').innerHTML = '';
    return;
  }
  const { commands } = await fetch(
    `/api/commands/${encodeURIComponent(session)}`
  ).then(r => r.json());

  document.getElementById('quick-commands').innerHTML = commands.map((c, i) => `
    <button class="quick-cmd-btn"
            onclick="runQuickCommand(${JSON.stringify(c.command)})"
            title="${esc(c.command)}">
      ${esc(c.label)}
    </button>
    <button class="btn-kill" onclick="deleteQuickCommand(${i})" title="Remove">✕</button>
  `).join('');
}

function runQuickCommand(cmd) {
  if (!state.currentSession || !state.socket?.connected) return;
  // Exit copy-mode if active
  if (state.inCopyMode) {
    state.socket.emit('scroll', { session: state.currentSession, command: 'exit' });
    state.inCopyMode = false;
  }
  state.socket.emit('input', { session: state.currentSession, data: cmd + '\r' });
}

async function addQuickCommand() {
  const label = document.getElementById('cmd-label').value.trim();
  const cmd   = document.getElementById('cmd-value').value.trim();
  if (!label || !cmd || !state.currentSession) return;

  await fetch(`/api/commands/${encodeURIComponent(state.currentSession)}`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ label, command: cmd }),
  });
  document.getElementById('cmd-label').value = '';
  document.getElementById('cmd-value').value = '';
  loadQuickCommands(state.currentSession);
}

async function deleteQuickCommand(index) {
  await fetch(
    `/api/commands/${encodeURIComponent(state.currentSession)}/${index}`,
    { method: 'DELETE' }
  );
  loadQuickCommands(state.currentSession);
}

// Call loadQuickCommands(name) whenever the active session changes.
// Example: hook into activateSession():
//   const _origActivate = activateSession;
//   activateSession = name => { _origActivate(name); loadQuickCommands(name); };
