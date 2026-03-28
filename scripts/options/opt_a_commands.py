"""
OPTION A — Quick Commands (per-session button palette)
Adds GET/POST/DELETE routes to manage commands saved in commands.json.

Wire into routes.py:
    from opt_a_commands import register_command_routes
    register_command_routes(app)
"""
import json
import os
from flask import jsonify, request

COMMANDS_FILE = 'commands.json'


def _load():
    if not os.path.exists(COMMANDS_FILE):
        return {}
    with open(COMMANDS_FILE, 'r') as f:
        return json.load(f)


def _save(data):
    tmp = COMMANDS_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, COMMANDS_FILE)


def register_command_routes(app):

    @app.route('/api/commands/<session>', methods=['GET'])
    def get_commands(session):
        return jsonify({'commands': _load().get(session, [])})

    @app.route('/api/commands/<session>', methods=['POST'])
    def add_command(session):
        data  = request.get_json() or {}
        label = data.get('label', '').strip()
        cmd   = data.get('command', '').strip()
        if not label or not cmd:
            return jsonify({'error': 'label and command required'}), 400
        store = _load()
        store.setdefault(session, []).append({'label': label, 'command': cmd})
        _save(store)
        return jsonify({'status': 'ok'})

    @app.route('/api/commands/<session>/<int:index>', methods=['DELETE'])
    def delete_command(session, index):
        store = _load()
        cmds  = store.get(session, [])
        if 0 <= index < len(cmds):
            cmds.pop(index)
            store[session] = cmds
            _save(store)
        return jsonify({'status': 'ok'})
