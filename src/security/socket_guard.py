"""
Bristlecone Logic - Runtime Security Engine
Deterministic Pre-Socket Guard & Egress Pinning Module
"""
import ipaddress
import socket
from typing import Tuple

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # AWS/GCP/Cloud Metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),     # Multicast
    ipaddress.ip_network("240.0.0.0/4"),     # Reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

class SecurityException(Exception):
    """Raised when an outbound connection violates network security policies."""
    pass

class SocketGuard:
    @staticmethod
    def inspect_and_resolve(hostname: str) -> str:
        """
        Resolves hostname to IP and verifies it against restricted address spaces.
        Returns the validated IP string.
        """
        try:
            addr_info = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise SecurityException(f"DNS resolution failure for host '{hostname}': {str(e)}")

        if not addr_info:
            raise SecurityException(f"No address records found for host '{hostname}'")

        resolved_ip = addr_info[0][4][0]
        ip_obj = ipaddress.ip_address(resolved_ip)

        for blocked in BLOCKED_NETWORKS:
            if ip_obj in blocked:
                raise SecurityException(
                    f"Egress violation: Target '{hostname}' resolved to blocked address space {resolved_ip}"
                )

        return resolved_ip

    @classmethod
    def create_pinned_connection(cls, hostname: str, port: int, timeout: float = 5.0) -> Tuple[socket.socket, str]:
        """
        Performs atomic resolution and directly opens a pinned TCP socket to the validated IP.
        Bypasses subsequent OS/library resolver calls to defeat TOCTOU DNS rebinding.
        """
        pinned_ip = cls.inspect_and_resolve(hostname)
        family = socket.AF_INET6 if ":" in pinned_ip else socket.AF_INET

        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((pinned_ip, port))
        except Exception as e:
            sock.close()
            raise ConnectionError(f"Failed to connect to pinned IP {pinned_ip}:{port} - {str(e)}")

        return sock, pinned_ip
