"""
OPTION E — Agent/Service Registry (YAML config)
Loads a list of named agents/services from config.yaml.
Each agent can be local_shell or docker type.

Wire into server.py:
    from opt_e_registry import AgentRegistry, register_registry_routes
    registry = AgentRegistry('config.yaml')
    app.config['managers']['registry'] = registry
    register_registry_routes(app)

Requires: pyyaml
"""
import yaml
import os


VALID_STATUSES = frozenset({
    'configured', 'starting', 'running', 'stopping', 'stopped', 'error', 'unknown'
})


class Agent:
    def __init__(self, raw: dict, base_dir: str):
        self.name      = raw['name']
        self.type      = raw.get('type', 'local_shell')   # local_shell | docker
        self.container = raw.get('container', f'app-{self.name}')
        self.cwd       = os.path.abspath(
                            os.path.join(base_dir, raw.get('cwd', '.')))
        self.readme    = raw.get('readme', 'README.md')
        self.tags      = raw.get('tags', [])
        self.auto_start = raw.get('auto_start', False)
        self._status   = 'unknown'

    @property
    def status(self): return self._status

    @status.setter
    def status(self, v):
        if v in VALID_STATUSES:
            self._status = v

    def to_dict(self):
        return {
            'name':      self.name,
            'type':      self.type,
            'container': self.container,
            'cwd':       self.cwd,
            'tags':      self.tags,
            'status':    self._status,
        }


class AgentRegistry:
    def __init__(self, config_path: str):
        self.config_path = os.path.abspath(config_path)
        self._agents: dict[str, Agent] = {}
        self.reload()

    def reload(self):
        with open(self.config_path, 'r') as f:
            raw = yaml.safe_load(f)
        base = os.path.dirname(self.config_path)
        self._agents = {
            a['name']: Agent(a, base)
            for a in raw.get('agents', [])
        }

    def all(self): return list(self._agents.values())
    def get(self, name): return self._agents.get(name)
    def names(self): return list(self._agents.keys())


def register_registry_routes(app):

    def reg():
        return app.config['managers']['registry']

    from flask import jsonify

    @app.route('/api/agents', methods=['GET'])
    def list_agents():
        return jsonify({'agents': [a.to_dict() for a in reg().all()]})

    @app.route('/api/agents/<name>', methods=['GET'])
    def get_agent(name):
        agent = reg().get(name)
        if not agent:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'agent': agent.to_dict()})
