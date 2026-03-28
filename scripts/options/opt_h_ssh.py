"""
OPTION H — SSH Remote Execution
Run commands on remote hosts and download files via SFTP.

Requires: paramiko>=3.4.0

Usage:
    runner = SSHRunner('192.168.1.100', 'ubuntu', key_file='~/.ssh/id_rsa')
    runner.connect()
    rc, out, err = runner.run('uname -a')
    runner.get_file('/remote/results.json', '/local/results.json')
    runner.close()
"""
import paramiko
import threading
import time
import logging

log = logging.getLogger(__name__)


class SSHRunner:
    def __init__(self, host, user, key_file=None, password=None,
                 port=22, timeout=30, retry_attempts=3, retry_delay=5):
        self._cfg = dict(hostname=host, username=user, port=port, timeout=timeout)
        if key_file:
            import os
            self._cfg['key_filename'] = os.path.expanduser(key_file)
        elif password:
            self._cfg['password'] = password

        self.retry_attempts = retry_attempts
        self.retry_delay    = retry_delay
        self._client        = None
        self._lock          = threading.Lock()
        self._connected     = False

    def connect(self):
        """Connect with retry. Raises on final failure."""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(**self._cfg)
                self._client    = client
                self._connected = True
                log.info('SSH connected to %s', self._cfg['hostname'])
                return
            except Exception as e:
                log.warning('SSH connect attempt %d failed: %s', attempt, e)
                if attempt < self.retry_attempts:
                    time.sleep(self.retry_delay)
        raise ConnectionError(f"SSH: could not connect to {self._cfg['hostname']} after {self.retry_attempts} attempts")

    @property
    def is_connected(self):
        return self._connected and self._client is not None

    def run(self, command: str, timeout: int = 60):
        """Execute command. Returns (exit_code, stdout, stderr)."""
        if not self.is_connected:
            self.connect()
        with self._lock:
            _, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return exit_code, stdout.read().decode('utf-8', errors='replace'), \
                   stderr.read().decode('utf-8', errors='replace')

    def get_file(self, remote_path: str, local_path: str):
        """Download a file via SFTP. Returns (success, error)."""
        try:
            with self._client.open_sftp() as sftp:
                sftp.get(remote_path, local_path)
            return True, None
        except Exception as e:
            return False, str(e)

    def put_file(self, local_path: str, remote_path: str):
        """Upload a file via SFTP. Returns (success, error)."""
        try:
            with self._client.open_sftp() as sftp:
                sftp.put(local_path, remote_path)
            return True, None
        except Exception as e:
            return False, str(e)

    def close(self):
        if self._client:
            self._client.close()
            self._client    = None
            self._connected = False
