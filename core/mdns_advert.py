# core/mdns_advert.py
from __future__ import annotations
from contextlib import suppress
from zeroconf import Zeroconf, ServiceInfo
import socket

class MdnsAdvert:
    def __init__(self):
        self.zeroconf = None
        self.info = None

    def _lan_ip(self) -> str:
        ip = "127.0.0.1"
        with suppress(Exception):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
        return ip

    def start(self, port: int, instance_name: str = "TempSensor Hub", hostname: str = "temps-hub.local."):
        ip = self._lan_ip()
        addr = socket.inet_aton(ip)
        self.info = ServiceInfo(
            type_="_http._tcp.local.",
            name=f"{instance_name}._http._tcp.local.",
            addresses=[addr],
            port=port,
            properties={},
            server=hostname,
        )
        self.zeroconf = Zeroconf()
        self.zeroconf.register_service(self.info)
        return ip

    def stop(self):
        with suppress(Exception):
            if self.zeroconf and self.info:
                self.zeroconf.unregister_service(self.info)
        with suppress(Exception):
            if self.zeroconf:
                self.zeroconf.close()
        self.zeroconf = None
        self.info = None
