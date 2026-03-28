"""
OPTION B — Docker Container Lifecycle Management
Routes: GET status, POST start/stop/restart.
Emits container_status socket event after each action.

Wire into server.py:
    from opt_b_docker import register_docker_routes
    register_docker_routes(app, socketio)
"""
import subprocess
from flask import jsonify

_STATE_MAP = {
    'running': 'running',
    'exited':  'stopped',
    'paused':  'stopped',
    'created': 'stopped',
    'dead':    'error',
}


def container_status(name):
    r = subprocess.run(
        ['docker', 'inspect', '--format', '{{.State.Status}}', name],
        capture_output=True, text=True, timeout=5
    )
    if r.returncode != 0:
        return 'unknown'
    return _STATE_MAP.get(r.stdout.strip(), 'unknown')


def container_action(name, action):
    """Returns (success: bool, error: str)."""
    r = subprocess.run(['docker', action, name],
                       capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stderr.strip()


def register_docker_routes(app, socketio):

    @app.route('/api/docker/<name>/status', methods=['GET'])
    def docker_status(name):
        return jsonify({'name': name, 'status': container_status(name)})

    @app.route('/api/docker/<name>/<action>', methods=['POST'])
    def docker_action(name, action):
        if action not in ('start', 'stop', 'restart'):
            return jsonify({'error': 'invalid action'}), 400
        ok, err = container_action(name, action)
        status  = container_status(name)
        # Broadcast new status to all connected clients
        socketio.emit('container_status', {'name': name, 'status': status})
        return jsonify({'status': 'ok' if ok else 'error', 'container_status': status, 'error': err})
