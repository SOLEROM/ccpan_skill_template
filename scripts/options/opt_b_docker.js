// OPTION B — Docker frontend
// Renders per-agent start/stop/restart controls and reacts to container_status events.
//
// Assumes state.agents = [{name, type, status}, ...]
// Assumes state.socket is the Socket.IO connection.

// Listen for status pushes from the server
function initDockerEvents() {
  state.socket.on('container_status', ({ name, status }) => {
    const agent = state.agents?.find(a => a.name === name);
    if (agent) {
      agent.status = status;
      renderAgentControls(name);
    }
  });
}

function renderDockerControls(agent) {
  if (agent.type !== 'docker') return '';
  const { name, status } = agent;
  return `
    <div class="docker-controls">
      <span class="status-badge s-${esc(status)}">${esc(status)}</span>
      ${status !== 'running'
        ? `<button onclick="dockerAction('${esc(name)}','start')">▶ Start</button>`
        : ''}
      ${status === 'running'
        ? `<button onclick="dockerAction('${esc(name)}','stop')">■ Stop</button>`
        : ''}
      ${status === 'running'
        ? `<button onclick="dockerAction('${esc(name)}','restart')">↺ Restart</button>`
        : ''}
    </div>`;
}

async function dockerAction(name, action) {
  // Optimistic UI — show transitional state immediately
  const agent = state.agents?.find(a => a.name === name);
  if (agent) {
    agent.status = action === 'stop' ? 'stopping' : 'starting';
    renderAgentControls(name);
  }

  const data = await fetch(`/api/docker/${encodeURIComponent(name)}/${action}`, {
    method: 'POST',
  }).then(r => r.json());

  if (data.status !== 'ok' && agent) {
    // Revert on error
    agent.status = action === 'stop' ? 'running' : 'stopped';
    renderAgentControls(name);
    alert(data.error || 'Docker action failed');
  }
  // Actual status will arrive via container_status socket event
}

// Stub — replace with your actual agent card rendering
function renderAgentControls(name) {
  const agent = state.agents?.find(a => a.name === name);
  if (!agent) return;
  const el = document.getElementById(`agent-controls-${name}`);
  if (el) el.innerHTML = renderDockerControls(agent);
}
