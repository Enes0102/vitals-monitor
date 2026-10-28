import socket
from concurrent.futures import ThreadPoolExecutor


class HostResolver:
    def __init__(self, enabled=True, workers=4):
        self.enabled = enabled
        self.cache = {}
        self.pending = set()
        self.pool = ThreadPoolExecutor(max_workers=workers) if enabled else None

    def _lookup(self, ip):
        try:
            host = socket.gethostbyaddr(ip)[0]
        except (OSError, UnicodeError):
            host = ""
        self.cache[ip] = host
        self.pending.discard(ip)

    def lookup(self, ip):
        if not self.enabled or not ip:
            return ""
        if ip in self.cache:
            return self.cache[ip]
        if ip not in self.pending:
            self.pending.add(ip)
            self.pool.submit(self._lookup, ip)
        return None

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=False, cancel_futures=True)
