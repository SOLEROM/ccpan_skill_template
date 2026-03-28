"""
TmuxManager — wraps all tmux CLI operations.
Uses a custom socket (-L <socket>) to isolate sessions from the user's own tmux.
"""
import subprocess
import os


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
        """Return session name with prefix, idempotent."""
        return name if name.startswith(self.prefix) else f'{self.prefix}{name}'

    def create_session(self, name, cwd=None, shell_cmd=None):
        """Create a detached tmux session.

        shell_cmd: if set, becomes the direct process (e.g. 'docker exec -it ...')
                   so the session exits cleanly when that command exits, instead
                   of dropping to a host shell.
        """
        full = self.full_name(name)
        args = ['new-session', '-d', '-s', full,
                '-x', str(self.default_cols), '-y', str(self.default_rows)]
        if cwd and os.path.isdir(cwd):
            args += ['-c', cwd]
        if shell_cmd:
            args += ['--', 'bash', '-c', shell_cmd]
        self._run(*args)
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
        """Send a signal to the foreground process via tmux key binding."""
        sig_map = {'SIGINT': 'C-c', 'SIGTSTP': 'C-z', 'SIGQUIT': 'C-\\'}
        key = sig_map.get(sig, 'C-c')
        self._run('send-keys', '-t', self.full_name(name), key, timeout=5)

    def resize_window(self, name, cols, rows):
        self._run('resize-window', '-t', self.full_name(name),
                  '-x', str(max(10, cols)), '-y', str(max(3, rows)))

    def enter_copy_mode(self, name):
        self._run('copy-mode', '-t', self.full_name(name))

    def exit_copy_mode(self, name):
        """Exit copy-mode by sending 'q'."""
        self._run('send-keys', '-t', self.full_name(name), 'q', timeout=5)

    def scroll(self, name, direction, lines=3):
        """Scroll within tmux copy-mode using vi key bindings."""
        full = self.full_name(name)
        # vi copy-mode keys
        key_map = {
            'up':        'k' * min(lines, 20),
            'down':      'j' * min(lines, 20),
            'page_up':   '\x02',   # C-b
            'page_down': '\x06',   # C-f
            'top':       'g',
            'bottom':    'G',
        }
        key = key_map.get(direction)
        if key:
            self._run('send-keys', '-t', full, key, timeout=5)
