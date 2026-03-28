"""
OPTION C — Markdown File Viewer & Editor
Serves and saves .md files relative to a base directory.
Security: path traversal rejection, .md-only, 1 MB limit, atomic writes.

Wire into routes.py:
    from opt_c_markdown import register_markdown_routes
    register_markdown_routes(app, base_dir='/path/to/docs')
"""
import os
from flask import jsonify, request

MAX_SIZE = 1_000_000  # 1 MB


def _resolve(base_dir, rel_path):
    """Return (abs_path, error). Rejects traversal and non-.md files."""
    abs_path = os.path.normpath(os.path.join(base_dir, rel_path))
    base_abs = os.path.abspath(base_dir)
    if not (abs_path.startswith(base_abs + os.sep) or abs_path == base_abs):
        return None, 'Path traversal rejected'
    if not abs_path.endswith('.md'):
        return None, 'Only .md files are allowed'
    return abs_path, None


def _atomic_write(path, content):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp, path)


def register_markdown_routes(app, base_dir='.'):
    base_dir = os.path.abspath(base_dir)

    @app.route('/api/files/<path:rel_path>', methods=['GET'])
    def read_md(rel_path):
        path, err = _resolve(base_dir, rel_path)
        if err:
            return jsonify({'error': err}), 400
        if not os.path.exists(path):
            return jsonify({'content': '', 'path': rel_path})
        with open(path, 'r', encoding='utf-8') as f:
            return jsonify({'content': f.read(), 'path': rel_path})

    @app.route('/api/files/<path:rel_path>', methods=['POST'])
    def write_md(rel_path):
        content = (request.get_json() or {}).get('content', '')
        if len(content.encode('utf-8')) > MAX_SIZE:
            return jsonify({'error': 'Content too large (max 1 MB)'}), 400
        path, err = _resolve(base_dir, rel_path)
        if err:
            return jsonify({'error': err}), 400
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _atomic_write(path, content)
        return jsonify({'status': 'ok'})
