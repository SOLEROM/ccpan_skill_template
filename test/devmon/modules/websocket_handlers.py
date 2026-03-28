# modules/websocket_handlers.py
from flask_socketio import emit, join_room, leave_room
from flask import request


def register_websocket_handlers(socketio, app):

    def mgr():
        return app.config['managers']

    @socketio.on('connect')
    def on_connect():
        emit('connected', {'status': 'ok'})

    @socketio.on('disconnect')
    def on_disconnect():
        pty = mgr()['pty']
        # Remove client from all sessions it was in
        for full_name in list(pty.connections.keys()):
            pty.remove_client(full_name, request.sid)

    @socketio.on('subscribe')
    def on_subscribe(data):
        name = data.get('session', '')
        cols = int(data.get('cols', 220))
        rows = int(data.get('rows', 50))

        tmux = mgr()['tmux']
        pty  = mgr()['pty']

        if not tmux.session_exists(name):
            emit('error', {'message': f'Session {name!r} not found'})
            return

        join_room(tmux.full_name(name))
        pty.get_or_create(name, request.sid, cols, rows)
        emit('subscribed', {'session': tmux.full_name(name)})

    @socketio.on('unsubscribe')
    def on_unsubscribe(data):
        name = data.get('session', '')
        tmux = mgr()['tmux']
        pty  = mgr()['pty']
        leave_room(tmux.full_name(name))
        pty.remove_client(name, request.sid)
        emit('unsubscribed', {'session': tmux.full_name(name)})

    @socketio.on('input')
    def on_input(data):
        name = data.get('session', '')
        keys = data.get('data', '')
        if name and keys:
            mgr()['pty'].send_input(name, keys)

    @socketio.on('resize')
    def on_resize(data):
        name = data.get('session', '')
        cols = int(data.get('cols', 80))
        rows = int(data.get('rows', 24))
        if name:
            mgr()['pty'].resize(name, cols, rows)

    @socketio.on('scroll')
    def on_scroll(data):
        name    = data.get('session', '')
        command = data.get('command', '')  # enter|exit|up|down|page_up|page_down|top|bottom
        lines   = int(data.get('lines', 3))
        tmux    = mgr()['tmux']
        if not name:
            return
        if command == 'enter':
            tmux.enter_copy_mode(name)
        elif command == 'exit':
            tmux.exit_copy_mode(name)
        elif command in ('up', 'down', 'page_up', 'page_down', 'top', 'bottom'):
            tmux.scroll(name, command, lines)

    @socketio.on('signal')
    def on_signal(data):
        name = data.get('session', '')
        sig  = data.get('signal', 'SIGINT')
        if name:
            mgr()['tmux'].send_signal(name, sig)
