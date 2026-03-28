# modules/routes.py
import json, os
from flask import jsonify, request, render_template

# Default quick-command palettes for devmon sessions
DEFAULT_COMMANDS = {
    'logs': [
        {'label': 'Disk Usage',     'command': 'df -h'},
        {'label': 'Memory',         'command': 'free -h'},
        {'label': 'Top Processes',  'command': 'ps aux --sort=-%cpu | head -20'},
        {'label': 'Tail Syslog',    'command': 'sudo journalctl -n 50 --no-pager 2>/dev/null || tail -50 /var/log/syslog 2>/dev/null || echo "No syslog available"'},
        {'label': 'Network Stats',  'command': 'ss -tuln'},
    ],
    'shell': [
        {'label': 'Disk Usage',     'command': 'df -h'},
        {'label': 'Memory',         'command': 'free -h'},
        {'label': 'List Processes', 'command': 'ps aux | head -20'},
        {'label': 'Who Am I',       'command': 'whoami && id'},
        {'label': 'Environment',    'command': 'env | sort | head -30'},
    ],
    'build': [
        {'label': 'Disk Usage',     'command': 'df -h'},
        {'label': 'Memory',         'command': 'free -h'},
        {'label': 'List Files',     'command': 'ls -lah'},
        {'label': 'Git Status',     'command': 'git status 2>/dev/null || echo "Not a git repo"'},
        {'label': 'Git Log',        'command': 'git log --oneline -10 2>/dev/null || echo "Not a git repo"'},
    ],
}

# Path to the runtime commands store
_COMMANDS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'commands.json')


def _load_commands():
    """Load commands.json, seeding it with defaults if it doesn't exist."""
    if not os.path.exists(_COMMANDS_FILE):
        _save_commands(DEFAULT_COMMANDS)
        return dict(DEFAULT_COMMANDS)
    try:
        with open(_COMMANDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_COMMANDS)


def _save_commands(data):
    tmp = _COMMANDS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, _COMMANDS_FILE)


def _strip_prefix(full_name, prefix):
    """Return the short name without the session prefix."""
    if full_name.startswith(prefix):
        return full_name[len(prefix):]
    return full_name


def register_routes(app):

    def mgr():
        return app.config['managers']

    # ── UI ─────────────────────────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    # ── Session management ─────────────────────────────────────────────────────

    @app.route('/api/sessions', methods=['GET'])
    def list_sessions():
        sessions = mgr()['tmux'].list_sessions()
        return jsonify({'sessions': sessions})

    @app.route('/api/sessions', methods=['POST'])
    def create_session():
        data = request.get_json() or {}
        name      = data.get('name', '').strip()
        cwd       = data.get('cwd')
        shell_cmd = data.get('shell_cmd')
        if not name:
            return jsonify({'error': 'name required'}), 400
        full = mgr()['tmux'].create_session(name, cwd=cwd, shell_cmd=shell_cmd)
        return jsonify({'status': 'ok', 'session': full})

    @app.route('/api/sessions/<name>', methods=['DELETE'])
    def kill_session(name):
        mgr()['tmux'].kill_session(name)
        return jsonify({'status': 'ok'})

    @app.route('/api/sessions/<name>/command', methods=['POST'])
    def run_command(name):
        data = request.get_json() or {}
        cmd = data.get('command', '')
        if cmd:
            mgr()['tmux'].send_keys(name, cmd + '\r')
        return jsonify({'status': 'ok'})

    # ── Quick Commands (Option A) ───────────────────────────────────────────────

    @app.route('/api/commands/<session>', methods=['GET'])
    def get_commands(session):
        store = _load_commands()
        tmux  = mgr()['tmux']
        # Try the full session name first, then the short name
        short = _strip_prefix(session, tmux.prefix)
        cmds = store.get(session, store.get(short, []))
        return jsonify({'commands': cmds, 'session': session})

    @app.route('/api/commands/<session>', methods=['POST'])
    def add_command(session):
        data  = request.get_json() or {}
        label = data.get('label', '').strip()
        cmd   = data.get('command', '').strip()
        if not label or not cmd:
            return jsonify({'error': 'label and command required'}), 400
        store = _load_commands()
        store.setdefault(session, []).append({'label': label, 'command': cmd})
        _save_commands(store)
        return jsonify({'status': 'ok'})

    @app.route('/api/commands/<session>/<int:index>', methods=['DELETE'])
    def delete_command(session, index):
        store = _load_commands()
        cmds = store.get(session, [])
        if index < 0 or index >= len(cmds):
            return jsonify({'error': 'index out of range'}), 400
        cmds.pop(index)
        store[session] = cmds
        _save_commands(store)
        return jsonify({'status': 'ok'})

    # ── Session info ────────────────────────────────────────────────────────────

    @app.route('/api/sessions/<name>/info', methods=['GET'])
    def session_info(name):
        tmux = mgr()['tmux']
        full = tmux.full_name(name)
        exists = tmux.session_exists(name)
        pty_conns = mgr()['pty'].connections
        connected = full in pty_conns
        client_count = len(pty_conns[full]['clients']) if connected else 0
        return jsonify({
            'session':      full,
            'short':        _strip_prefix(full, tmux.prefix),
            'exists':       exists,
            'pty_active':   connected,
            'client_count': client_count,
        })

    # ── Default sessions bootstrap ──────────────────────────────────────────────

    @app.route('/api/bootstrap', methods=['POST'])
    def bootstrap():
        """Create the default devmon sessions if they don't already exist."""
        tmux    = mgr()['tmux']
        created = []
        for sname in ('logs', 'shell', 'build'):
            if not tmux.session_exists(sname):
                full = tmux.create_session(sname)
                created.append(full)
        return jsonify({'status': 'ok', 'created': created})
