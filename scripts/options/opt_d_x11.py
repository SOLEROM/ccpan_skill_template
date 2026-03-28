"""
OPTION D — X11 GUI Panels (Xvfb + x11vnc + websockify → noVNC in browser)
System deps: xvfb, x11vnc, websockify  (apt install xvfb x11vnc websockify)
noVNC:       ship /static/js/novnc/ from https://github.com/novnc/noVNC

Architecture per panel:
  Xvfb :{N} → x11vnc rfbport {vnc_port} → websockify {ws_port}
  Browser: new RFB(el, 'ws://host:{ws_port}')

Wire into server.py:
    from opt_d_x11 import X11Manager, register_x11_routes
    x11 = X11Manager()
    app.config['managers']['x11'] = x11
    register_x11_routes(app)
    atexit.register(x11.stop_all)
"""
import subprocess
from flask import jsonify, request

# Fixed port assignments. Adjust if ports conflict.
PANELS = {
    0: {'display': 100, 'vnc_port': 5900, 'ws_port': 6100},
    1: {'display': 101, 'vnc_port': 5901, 'ws_port': 6101},
    2: {'display': 102, 'vnc_port': 5902, 'ws_port': 6102},
}


class X11Manager:
    def __init__(self):
        self.running = {}   # display_num → {xvfb, vnc, ws}

    def start(self, panel_index=0, width=1280, height=800):
        cfg     = PANELS[panel_index]
        dnum    = cfg['display']
        display = f':{dnum}'

        if dnum in self.running:
            return cfg, None  # already running

        try:
            xvfb = subprocess.Popen([
                'Xvfb', display, '-screen', '0', f'{width}x{height}x24',
                '-ac', '+extension', 'GLX', '-nolisten', 'tcp',
            ])
            vnc = subprocess.Popen([
                'x11vnc', '-display', display,
                '-rfbport', str(cfg['vnc_port']),
                '-nopw', '-forever', '-shared', '-noxdamage',
            ])
            ws = subprocess.Popen([
                'websockify', str(cfg['ws_port']),
                f"127.0.0.1:{cfg['vnc_port']}",
            ])
            self.running[dnum] = {'xvfb': xvfb, 'vnc': vnc, 'ws': ws}
            return cfg, None
        except FileNotFoundError as e:
            return None, f'Missing dependency: {e}'

    def stop(self, panel_index):
        dnum  = PANELS[panel_index]['display']
        procs = self.running.pop(dnum, {})
        for p in procs.values():
            try: p.terminate()
            except: pass

    def stop_all(self):
        for dnum in list(self.running.keys()):
            idx = next(i for i, c in PANELS.items() if c['display'] == dnum)
            self.stop(idx)

    def inject_display(self, tmux_manager, session_name, panel_index):
        """Export DISPLAY and GPU env vars into a tmux session."""
        dnum = PANELS[panel_index]['display']
        for k, v in {
            'DISPLAY': f':{dnum}',
            'GDK_BACKEND': 'x11',
            'QT_QPA_PLATFORM': 'xcb',
            'LIBGL_ALWAYS_SOFTWARE': '1',
            'GALLIUM_DRIVER': 'llvmpipe',
        }.items():
            tmux_manager.send_keys(session_name, f'export {k}={v}\r')


def register_x11_routes(app):

    def x11():
        return app.config['managers']['x11']

    @app.route('/api/x11/panels', methods=['GET'])
    def list_panels():
        return jsonify({'panels': [
            {'index': i, 'display': c['display'],
             'ws_port': c['ws_port'], 'vnc_port': c['vnc_port'],
             'running': c['display'] in x11().running}
            for i, c in PANELS.items()
        ]})

    @app.route('/api/x11/panel/<int:index>/connect', methods=['POST'])
    def connect_panel(index):
        if index not in PANELS:
            return jsonify({'error': 'invalid panel index'}), 400
        data = request.get_json() or {}
        cfg, err = x11().start(index,
                               width=data.get('width', 1280),
                               height=data.get('height', 800))
        if err:
            return jsonify({'error': err}), 500
        return jsonify({'status': 'ok', 'ws_port': cfg['ws_port'], 'display': cfg})

    @app.route('/api/x11/panel/<int:index>/stop', methods=['POST'])
    def stop_panel(index):
        x11().stop(index)
        return jsonify({'status': 'ok'})

    @app.route('/api/x11/panel/<int:index>/inject', methods=['POST'])
    def inject_display(index):
        data    = request.get_json() or {}
        session = data.get('session', '')
        if not session:
            return jsonify({'error': 'session required'}), 400
        tmux = app.config['managers']['tmux']
        x11().inject_display(tmux, session, index)
        return jsonify({'status': 'ok'})
