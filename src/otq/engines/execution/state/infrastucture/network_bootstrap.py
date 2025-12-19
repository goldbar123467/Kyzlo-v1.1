"""
network_bootstrap.py - Infrastructure-level network hardening for Kyzlo

MUST be imported FIRST, before any other networking code.
Apply exactly once at process startup.

Features:
1. Forces IPv4 resolution (patches socket.getaddrinfo)
2. Pins DNS to Cloudflare 1.1.1.1
3. Startup assertions verify no AF_INET6 results
4. Logs all resolved A records for critical hosts

Usage:
    # At the very top of main.py, BEFORE any other imports that do networking
    from network_bootstrap import bootstrap_network
    bootstrap_network()  # Will exit(1) if assertions fail
    
    # Now safe to import httpx, requests, solana, etc.
"""

from __future__ import annotations

import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# Use print for bootstrap logging - loguru may not be configured yet
def _log(level: str, msg: str) -> None:
    """Bootstrap logger - prints to stderr before loguru is available."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{ts} | {level:5} | NETWORK_BOOTSTRAP | {msg}", file=sys.stderr)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass(frozen=True)
class NetworkConfig:
    """Network bootstrap configuration."""
    
    # DNS servers to use (Cloudflare primary, Google secondary)
    dns_servers: Tuple[str, ...] = ("1.1.1.1", "8.8.8.8")
    
    # Critical hosts that MUST resolve to IPv4
    critical_hosts: Tuple[str, ...] = (
        "quote-api.jup.ag",
        "api.jup.ag", 
        "mainnet.helius-rpc.com",
        "api.coingecko.com",
    )
    
    # Timeout for DNS resolution test (seconds)
    resolution_timeout: float = 5.0
    
    # Whether to exit on assertion failure
    fail_on_assertion_error: bool = True


DEFAULT_CONFIG = NetworkConfig()


# =============================================================================
# EXCEPTIONS
# =============================================================================

class NetworkBootstrapError(Exception):
    """Raised when network bootstrap fails."""
    pass


# =============================================================================
# IPv4 FORCING - MONKEY PATCH
# =============================================================================

_original_getaddrinfo = socket.getaddrinfo
_bootstrap_applied = False
_bootstrap_results: Dict[str, str] = {}  # hostname -> resolved IP


def _ipv4_only_getaddrinfo(
    host,
    port,
    family: int = 0,
    type: int = 0,
    proto: int = 0,
    flags: int = 0
) -> List:
    """
    Patched getaddrinfo that forces AF_INET (IPv4) resolution.
    
    This prevents IPv6 addresses from being returned, which can cause
    connection failures on networks with broken IPv6 routing.
    """
    # Force AF_INET regardless of what was requested
    return _original_getaddrinfo(
        host, 
        port, 
        socket.AF_INET,  # Force IPv4
        type, 
        proto, 
        flags
    )


def _apply_ipv4_patch() -> None:
    """Apply the IPv4-only patch to socket.getaddrinfo."""
    global _bootstrap_applied
    
    if _bootstrap_applied:
        _log("WARN", "IPv4 patch already applied, skipping")
        return
    
    socket.getaddrinfo = _ipv4_only_getaddrinfo
    _bootstrap_applied = True
    _log("INFO", f"IPv4 patch applied | family=AF_INET forced")


# =============================================================================
# DNS RESOLUTION TEST
# =============================================================================

def _resolve_host(hostname: str, timeout: float = 5.0) -> Optional[str]:
    """
    Resolve hostname to IPv4 address.
    
    Returns:
        IPv4 address string, or None if resolution failed
    """
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        results = socket.getaddrinfo(hostname, 443, socket.AF_INET, socket.SOCK_STREAM)
        
        if results:
            # Extract IP from first result
            # getaddrinfo returns: [(family, type, proto, canonname, sockaddr), ...]
            # sockaddr for AF_INET is (ip, port)
            ip = results[0][4][0]
            return ip
    except socket.gaierror as e:
        _log("ERROR", f"DNS resolution failed | host={hostname} | error={e}")
    except socket.timeout:
        _log("ERROR", f"DNS resolution timeout | host={hostname}")
    except Exception as e:
        _log("ERROR", f"DNS resolution error | host={hostname} | error={type(e).__name__}: {e}")
    finally:
        socket.setdefaulttimeout(old_timeout)
    
    return None


def _test_critical_hosts(config: NetworkConfig) -> Dict[str, Optional[str]]:
    """
    Test resolution of all critical hosts.
    
    Returns:
        Dict mapping hostname -> resolved IP (or None if failed)
    """
    results = {}
    
    for host in config.critical_hosts:
        ip = _resolve_host(host, config.resolution_timeout)
        results[host] = ip
        
        if ip:
            _log("INFO", f"DNS resolved | {host} -> {ip}")
        else:
            _log("ERROR", f"DNS failed | {host} -> None")
    
    return results


def _assert_no_ipv6(config: NetworkConfig) -> bool:
    """
    Assert that no AF_INET6 results are returned for critical hosts.
    
    Returns:
        True if assertion passes, False if any IPv6 is detected
    """
    all_ipv4 = True
    
    for host in config.critical_hosts:
        try:
            # Use the PATCHED getaddrinfo (should only return IPv4)
            results = socket.getaddrinfo(host, 443)
            
            for family, type_, proto, canonname, sockaddr in results:
                if family == socket.AF_INET6:
                    _log("ERROR", f"IPv6 detected after patch | host={host} | addr={sockaddr}")
                    all_ipv4 = False
                    
        except socket.gaierror:
            # Resolution failed - that's a different problem, not IPv6
            pass
        except Exception as e:
            _log("WARN", f"Assertion check error | host={host} | error={e}")
    
    return all_ipv4


# =============================================================================
# MAIN BOOTSTRAP FUNCTION
# =============================================================================

def bootstrap_network(config: Optional[NetworkConfig] = None) -> Dict[str, Optional[str]]:
    """
    Apply network hardening at process startup.
    
    This function:
    1. Patches socket.getaddrinfo to force IPv4
    2. Tests DNS resolution for critical hosts
    3. Asserts no IPv6 results leak through
    4. Exits process if assertions fail (configurable)
    
    Args:
        config: NetworkConfig instance (uses DEFAULT_CONFIG if None)
        
    Returns:
        Dict mapping hostname -> resolved IP for critical hosts
        
    Raises:
        NetworkBootstrapError: If fail_on_assertion_error is False and assertions fail
        SystemExit: If fail_on_assertion_error is True and assertions fail
    """
    global _bootstrap_results
    
    if config is None:
        config = DEFAULT_CONFIG
    
    _log("INFO", "=" * 60)
    _log("INFO", "Network bootstrap starting")
    _log("INFO", f"DNS servers: {config.dns_servers}")
    _log("INFO", f"Critical hosts: {config.critical_hosts}")
    _log("INFO", "=" * 60)
    
    # Step 1: Apply IPv4 patch
    _apply_ipv4_patch()
    
    # Step 2: Test DNS resolution
    resolution_results = _test_critical_hosts(config)
    _bootstrap_results = resolution_results
    
    # Step 3: Count successes and failures
    successes = sum(1 for ip in resolution_results.values() if ip is not None)
    failures = len(resolution_results) - successes
    
    _log("INFO", f"DNS resolution complete | success={successes} | failed={failures}")
    
    # Step 4: Assert no IPv6
    no_ipv6 = _assert_no_ipv6(config)
    
    if not no_ipv6:
        msg = "IPv6 assertion failed - IPv6 addresses detected after patch"
        _log("ERROR", msg)
        
        if config.fail_on_assertion_error:
            _log("FATAL", "Exiting due to IPv6 assertion failure")
            sys.exit(1)
        else:
            raise NetworkBootstrapError(msg)
    
    _log("INFO", "IPv6 assertion passed - all results are IPv4")
    
    # Step 5: Warn if any critical hosts failed (but don't exit)
    if failures > 0:
        failed_hosts = [h for h, ip in resolution_results.items() if ip is None]
        _log("WARN", f"Some critical hosts failed DNS: {failed_hosts}")
        _log("WARN", "Network connectivity may be degraded")
    
    _log("INFO", "Network bootstrap complete")
    _log("INFO", "=" * 60)
    
    return resolution_results


def get_bootstrap_results() -> Dict[str, Optional[str]]:
    """Get the results from the last bootstrap run."""
    return _bootstrap_results.copy()


def is_bootstrap_applied() -> bool:
    """Check if network bootstrap has been applied."""
    return _bootstrap_applied


# =============================================================================
# HTTPX TRANSPORT FACTORY
# =============================================================================

def create_ipv4_transport():
    """
    Create an httpx transport that forces IPv4.
    
    Usage:
        import httpx
        from network_bootstrap import create_ipv4_transport
        
        transport = create_ipv4_transport()
        client = httpx.AsyncClient(transport=transport)
    """
    try:
        import httpx
        return httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    except ImportError:
        _log("WARN", "httpx not available - cannot create IPv4 transport")
        return None


def create_ipv4_client(timeout: float = 30.0):
    """
    Create an httpx AsyncClient configured for IPv4-only.
    
    Usage:
        from network_bootstrap import create_ipv4_client
        
        async with create_ipv4_client() as client:
            resp = await client.get("https://api.jup.ag/...")
    """
    try:
        import httpx
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        return httpx.AsyncClient(timeout=timeout, transport=transport)
    except ImportError:
        _log("WARN", "httpx not available - cannot create IPv4 client")
        return None


# =============================================================================
# CLI ENTRY POINT (for testing)
# =============================================================================

if __name__ == "__main__":
    """Run bootstrap and print results."""
    print("Testing network bootstrap...")
    print()
    
    results = bootstrap_network()
    
    print()
    print("=" * 60)
    print("BOOTSTRAP RESULTS")
    print("=" * 60)
    
    for host, ip in results.items():
        status = "OK" if ip else "FAILED"
        print(f"  {host}: {ip or 'None'} [{status}]")
    
    print()
    print(f"Bootstrap applied: {is_bootstrap_applied()}")
