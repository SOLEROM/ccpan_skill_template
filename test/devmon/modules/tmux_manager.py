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
        sig_map = {'SIGINT': 'C-c', 'SIGTSTP': 'C-z', 'SIGQUIT': 'C-\\'}
        key = sig_map.get(sig, 'C-c')
        self._run('send-keys', '-t', self.full_name(name), key, timeout=5)

    def resize_window(self, name, cols, rows):
        self._run('resize-window', '-t', self.full_name(name),
                  '-x', str(max(10, cols)), '-y', str(max(3, rows)))

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
            self._run('send-keys', '-t', full,
                      'k' * min(lines, 20) if direction == 'up' else
                      'j' * min(lines, 20) if direction == 'down' else
                      '\x02' if direction == 'page_up' else '\x06',
                      timeout=5)
