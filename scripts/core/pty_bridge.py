"""
PtyBridge — forks a PTY that attaches to a tmux session and streams all
output to connected Socket.IO clients in real-time.

Key behaviors:
- One PTY per session, shared by all clients in the SocketIO room.
- Non-blocking I/O: select() with 50ms timeout, reads up to 16 KB/chunk.
- Escape sequence filtering: strips OSC, DCS, DA to prevent terminal injection.
- Deferred 5-second cleanup after last client disconnects (handles page refresh).
- Input fallback: if PTY write fails, uses tmux send-keys.
"""
import os
import pty
import fcntl
import select
import struct
import termios
import threading
import re
import time
import logging

log = logging.getLogger(__name__)

# ── Escape sequence filters ────────────────────────────────────────────────────
# Strip sequences that can leak terminal state or enable clipboard/color attacks.
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


# ── PtyBridge ─────────────────────────────────────────────────────────────────

class PtyBridge:
    def __init__(self, tmux_manager, socketio):
        self.tmux = tmux_manager
        self.socketio = socketio
        self.connections = {}   # full_session_name → conn dict
        self._lock = threading.Lock()

    def get_or_create(self, name, client_sid, cols=220, rows=50):
        """Return existing PTY connection or spawn a new one, adding client_sid."""
        full = self.tmux.full_name(name)
        with self._lock:
            if full not in self.connections:
                master_fd, pid = self._spawn(full, cols, rows)
                reader_t, stop_ev = self._start_reader(full, master_fd)
                self.connections[full] = {
                    'master_fd': master_fd,
                    'pid': pid,
                    'reader': reader_t,
                    'stop': stop_ev,
                    'clients': set(),
                }
            conn = self.connections[full]
            conn['clients'].add(client_sid)
            return conn

    def _spawn(self, full_name, cols, rows):
        self.tmux.resize_window(full_name, cols, rows)
        pid, master_fd = pty.fork()
        if pid == 0:  # child process
            os.environ['TERM'] = 'xterm-256color'
            os.execlp('tmux', 'tmux', '-L', self.tmux.socket,
                      'attach', '-t', full_name)
            os._exit(1)
        # parent: set non-blocking
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
            log.debug('reader stopped for %s', full_name)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        return t, stop_event

    def send_input(self, name, data: str):
        """Write keystrokes to the PTY, falling back to tmux send-keys."""
        full = self.tmux.full_name(name)
        conn = self.connections.get(full)
        if conn:
            try:
                os.write(conn['master_fd'], data.encode('utf-8'))
                return True
            except OSError:
                pass
        self.tmux.send_keys(name, data)
        return False

    def resize(self, name, cols, rows):
        full = self.tmux.full_name(name)
        conn = self.connections.get(full)
        if conn:
            self._set_winsize(conn['master_fd'], rows, cols)
        self.tmux.resize_window(name, cols, rows)

    def remove_client(self, name, sid):
        """Remove a client; schedule PTY cleanup if no clients remain."""
        full = self.tmux.full_name(name)
        conn = self.connections.get(full)
        if not conn:
            return
        conn['clients'].discard(sid)
        if not conn['clients']:
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
        """Stop all reader threads and close all FDs (call from atexit)."""
        with self._lock:
            for conn in self.connections.values():
                conn['stop'].set()
                try:
                    os.close(conn['master_fd'])
                except OSError:
                    pass
            self.connections.clear()
