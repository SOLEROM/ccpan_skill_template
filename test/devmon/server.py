#!/usr/bin/env python3
"""
devmon — Developer Monitor Panel
Run with: python server.py [--host HOST] [--port PORT] [--public]
"""
import atexit, argparse
from flask import Flask
from flask_socketio import SocketIO
from modules.tmux_manager import TmuxManager
from modules.pty_bridge import PtyBridge
from modules.routes import register_routes
from modules.websocket_handlers import register_websocket_handlers


def create_app(config: dict = None):
    app = Flask(__name__)
    socketio = SocketIO(app, cors_allowed_origins='*', async_mode='eventlet')

    cfg = config or {}
    tmux = TmuxManager(
        socket_name=cfg.get('tmux_socket', 'devmon'),
        prefix=cfg.get('session_prefix', 'devmon-'),
        scrollback=cfg.get('scrollback', 10000),
    )
    pty = PtyBridge(tmux, socketio)

    app.config['managers'] = {'tmux': tmux, 'pty': pty}

    register_routes(app)
    register_websocket_handlers(socketio, app)

    atexit.register(pty.cleanup_all)
    return app, socketio


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='devmon — Developer Monitor Panel')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--public', action='store_true',
                        help='Bind to 0.0.0.0 (all interfaces)')
    args = parser.parse_args()

    app, socketio = create_app()
    host = '0.0.0.0' if args.public else args.host
    print(f'devmon starting on http://{host}:{args.port}')
    socketio.run(app, host=host, port=args.port, debug=False)
