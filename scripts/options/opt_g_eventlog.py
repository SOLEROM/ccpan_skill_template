"""
OPTION G — Append-only Audit Event Log (JSONL)
Thread-safe, sequence-numbered, timestamped log file.

Usage:
    log = EventLog('events.jsonl')
    log.append('session_created', {'name': 'myapp-shell'})
    log.append('command_sent',    {'session': 'myapp-shell', 'cmd': 'ls'}, user={'name': 'alice'})
    events = log.tail(50)

Common event types:
    session_created, session_killed
    command_sent, signal_sent
    container_started, container_stopped, container_restarted
    file_saved
    user_connected, user_disconnected
"""
import json
import threading
from datetime import datetime, timezone


class EventLog:
    def __init__(self, path: str):
        self.path  = path
        self._lock = threading.Lock()
        self._seq  = self._init_seq()

    def _init_seq(self):
        """Resume sequence from last entry in existing log."""
        try:
            with open(self.path, 'r') as f:
                lines = f.readlines()
            if lines:
                return json.loads(lines[-1]).get('seq', 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return 0

    def append(self, event_type: str, data: dict, user: dict = None) -> dict:
        with self._lock:
            self._seq += 1
            entry = {
                'seq':  self._seq,
                'ts':   datetime.now(timezone.utc).isoformat(),
                'type': event_type,
                'data': data,
            }
            if user:
                entry['user'] = user
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            return entry

    def tail(self, n: int = 100) -> list:
        """Return the last n entries."""
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            return [json.loads(l) for l in lines[-n:]]
        except FileNotFoundError:
            return []

    def all(self) -> list:
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                return [json.loads(l) for l in f if l.strip()]
        except FileNotFoundError:
            return []
