// OPTION I — Resizable Split Panel
// Horizontal drag handle between left (terminal) and right (info/markdown/etc) panels.
// After resize, re-fits the xterm.js terminal and emits a resize event to the server.
//
// HTML needed:
//   <div id="workspace">
//     <div id="left-panel">  <!-- terminal goes here --> </div>
//     <div id="resize-handle"></div>
//     <div id="right-panel"> <!-- sidebar content  --> </div>
//   </div>
//
// CSS: see opt_i_splitter.css

function initSplitter() {
  const handle = document.getElementById('resize-handle');
  const left   = document.getElementById('left-panel');
  let dragging = false, startX = 0, startW = 0;

  handle.addEventListener('mousedown', e => {
    dragging = true;
    startX   = e.clientX;
    startW   = left.getBoundingClientRect().width;
    document.body.style.cursor     = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const workspace = document.getElementById('workspace');
    const total     = workspace.getBoundingClientRect().width;
    const newW      = Math.min(Math.max(startW + e.clientX - startX, 200), total - 200);
    left.style.width = newW + 'px';
    // Re-fit terminal as we drag (optional — can be expensive; remove if sluggish)
    state.fitAddon?.fit();
  });

  document.addEventListener('mouseup', e => {
    if (!dragging) return;
    dragging = false;
    document.body.style.cursor     = '';
    document.body.style.userSelect = '';
    // Fit and report new terminal size
    state.fitAddon?.fit();
    if (state.currentSession && state.socket?.connected && state.terminal) {
      state.socket.emit('resize', {
        session: state.currentSession,
        cols:    state.terminal.cols,
        rows:    state.terminal.rows,
      });
    }
  });
}

// Call initSplitter() in your DOMContentLoaded handler.
