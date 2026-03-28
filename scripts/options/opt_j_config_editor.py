"""
OPTION J — Configuration YAML Editor in UI
Lets operators read and update the app's config.yaml from the browser.
Validates YAML before saving. Uses atomic write.

Wire into routes.py:
    from opt_j_config_editor import register_config_routes
    register_config_routes(app, config_path='config.yaml')

Requires: pyyaml
"""
import os
import yaml
from flask import jsonify, request


def register_config_routes(app, config_path='config.yaml'):
    config_path = os.path.abspath(config_path)

    @app.route('/api/config/yaml', methods=['GET'])
    def get_config_yaml():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return jsonify({'yaml': f.read()})
        except FileNotFoundError:
            return jsonify({'yaml': ''})

    @app.route('/api/config/yaml', methods=['POST'])
    def save_config_yaml():
        content = (request.get_json() or {}).get('yaml', '')
        # Validate before saving
        try:
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                return jsonify({'error': 'Top-level must be a YAML mapping (dict)'}), 400
        except yaml.YAMLError as e:
            return jsonify({'error': f'YAML parse error: {e}'}), 400

        tmp = config_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, config_path)
        return jsonify({'status': 'ok'})
