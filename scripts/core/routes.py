"""
Core REST routes.

GET    /                          → index.html
GET    /api/sessions              → list managed sessions
POST   /api/sessions              → create session  {name, cwd?, shell_cmd?}
DELETE /api/sessions/<name>       → kill session
POST   /api/sessions/<name>/command → send command  {command}
"""
from flask import jsonify, request, render_template


def register_routes(app):

    def mgr():
        return app.config['managers']

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/sessions', methods=['GET'])
    def list_sessions():
        return jsonify({'sessions': mgr()['tmux'].list_sessions()})

    @app.route('/api/sessions', methods=['POST'])
    def create_session():
        data      = request.get_json() or {}
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
        cmd  = data.get('command', '')
        if cmd:
            mgr()['tmux'].send_keys(name, cmd + '\r')
        return jsonify({'status': 'ok'})
