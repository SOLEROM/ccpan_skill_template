// OPTION D — X11 GUI Panels frontend
// Requires noVNC shipped at /static/js/novnc/core/rfb.js
//
// HTML needed (repeat for each panel index 0-2):
//   <div id="gui-panel-0" class="gui-panel">
//     <div class="gui-panel-header">
//       GUI 1
//       <button onclick="connectGuiPanel(0)">Connect</button>
//       <button onclick="stopGuiPanel(0)">Disconnect</button>
//       <button onclick="injectDisplay(0)">Set DISPLAY</button>
//     </div>
//     <div id="gui-canvas-0" class="gui-canvas"></div>
//   </div>

const guiPanels = [
  { index: 0, rfb: null, connected: false },
  { index: 1, rfb: null, connected: false },
  { index: 2, rfb: null, connected: false },
];

async function connectGuiPanel(index) {
  const res = await fetch(`/api/x11/panel/${index}/connect`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ width: 1280, height: 800 }),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  // Dynamically import noVNC RFB module
  const { default: RFB } = await import('/static/js/novnc/core/rfb.js');
  const canvas = document.getElementById(`gui-canvas-${index}`);
  const wsUrl  = `ws://${location.hostname}:${data.ws_port}`;

  // Disconnect existing connection if any
  if (guiPanels[index].rfb) {
    try { guiPanels[index].rfb.disconnect(); } catch (_) {}
  }

  const rfb = new RFB(canvas, wsUrl, { scaleViewport: true, resizeSession: false });
  rfb.addEventListener('connect',    () => { guiPanels[index].connected = true; });
  rfb.addEventListener('disconnect', () => { guiPanels[index].connected = false; });
  guiPanels[index].rfb = rfb;
}

async function stopGuiPanel(index) {
  if (guiPanels[index].rfb) {
    try { guiPanels[index].rfb.disconnect(); } catch (_) {}
    guiPanels[index].rfb       = null;
    guiPanels[index].connected = false;
  }
  await fetch(`/api/x11/panel/${index}/stop`, { method: 'POST' });
  document.getElementById(`gui-canvas-${index}`).innerHTML = '';
}

async function injectDisplay(index) {
  if (!state.currentSession) { alert('No active session'); return; }
  await fetch(`/api/x11/panel/${index}/inject`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ session: state.currentSession }),
  });
}
