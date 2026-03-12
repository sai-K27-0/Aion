"""
Service Discovery - mDNS/Bonjour for automatic server discovery on local network.

This service registers the Aion server on the local network so that
mobile and desktop clients can automatically find it without manual configuration.
"""

import asyncio
import socket
from typing import Optional
from dataclasses import dataclass

try:
    from zeroconf import ServiceInfo, Zeroconf, IPVersion
    from zeroconf.asyncio import AsyncZeroconf
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False

import logging

logger = logging.getLogger(__name__)


@dataclass
class ServerInfo:
    """Information about the discovered server."""
    name: str
    host: str
    port: int
    version: str
    api_path: str


class DiscoveryService:
    """
    Manages mDNS service advertisement and discovery.
    
    When started, advertises the Aion server on the local network
    using the service type "_aion._tcp.local."
    """
    
    SERVICE_TYPE = "_aion._tcp.local."
    SERVICE_NAME = "Aion Server._aion._tcp.local."
    
    def __init__(self, port: int = 8000, version: str = "0.3.8"):
        self.port = port
        self.version = version
        self.zeroconf: Optional[AsyncZeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self._running = False
        self._registered_ip: Optional[str] = None
        self._ip_check_task: Optional[asyncio.Task] = None
    
    def _get_local_ip(self) -> str:
        """Get the local IP address of this machine."""
        try:
            # Create a socket to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    async def start(self) -> bool:
        """
        Start advertising the server via mDNS.
        
        Returns True if successful, False if zeroconf is not available.
        """
        if not ZEROCONF_AVAILABLE:
            logger.warning("Zeroconf not available. Install with: pip install zeroconf")
            return False
        
        if self._running:
            return True
        
        try:
            local_ip = self._get_local_ip()
            
            # Create service info
            self.service_info = ServiceInfo(
                type_=self.SERVICE_TYPE,
                name=self.SERVICE_NAME,
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    "version": self.version,
                    "api": "/api/v1",
                    "sync": "/api/v1/sync",
                    "name": "Aion Server",
                },
            )
            
            # Create and start Zeroconf
            self.zeroconf = AsyncZeroconf(ip_version=IPVersion.V4Only)
            await self.zeroconf.async_register_service(self.service_info)
            
            self._running = True
            self._registered_ip = local_ip
            logger.info(f"mDNS service registered: {local_ip}:{self.port}")
            logger.info(f"Clients can discover server at: {self.SERVICE_TYPE}")

            # Start background IP change monitor
            self._ip_check_task = asyncio.create_task(self._monitor_ip_changes())

            return True
            
        except Exception as e:
            logger.error(f"Failed to start mDNS service: {e}")
            return False
    
    async def _monitor_ip_changes(self):
        """Periodically check if the local IP changed and re-register if needed."""
        while self._running:
            try:
                await asyncio.sleep(30)
                current_ip = self._get_local_ip()
                if current_ip != self._registered_ip and current_ip != "127.0.0.1":
                    logger.info(f"IP changed from {self._registered_ip} to {current_ip}, re-registering mDNS")
                    await self._re_register(current_ip)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"IP monitor error: {e}")

    async def _re_register(self, new_ip: str):
        """Unregister old service and register with new IP."""
        try:
            if self.service_info and self.zeroconf:
                await self.zeroconf.async_unregister_service(self.service_info)
            self.service_info = ServiceInfo(
                type_=self.SERVICE_TYPE,
                name=self.SERVICE_NAME,
                addresses=[socket.inet_aton(new_ip)],
                port=self.port,
                properties={
                    "version": self.version,
                    "api": "/api/v1",
                    "sync": "/api/v1/sync",
                    "name": "Aion Server",
                },
            )
            if self.zeroconf:
                await self.zeroconf.async_register_service(self.service_info)
            self._registered_ip = new_ip
            logger.info(f"mDNS re-registered with new IP: {new_ip}")
        except Exception as e:
            logger.error(f"Failed to re-register mDNS: {e}")

    async def stop(self):
        """Stop advertising the server."""
        if self._ip_check_task:
            self._ip_check_task.cancel()
            try:
                await self._ip_check_task
            except asyncio.CancelledError:
                pass
            self._ip_check_task = None

        if not self._running or not self.zeroconf:
            return

        try:
            if self.service_info:
                await self.zeroconf.async_unregister_service(self.service_info)
            await self.zeroconf.async_close()
            self._running = False
            self._registered_ip = None
            logger.info("mDNS service stopped")
        except Exception as e:
            logger.error(f"Error stopping mDNS service: {e}")
    
    def get_server_info(self) -> Optional[ServerInfo]:
        """Get information about this server."""
        if not self._running:
            return None
        
        return ServerInfo(
            name="Aion Server",
            host=self._get_local_ip(),
            port=self.port,
            version=self.version,
            api_path="/api/v1",
        )


# Singleton instance
_discovery_service: Optional[DiscoveryService] = None


def get_discovery_service(port: int = 8000) -> DiscoveryService:
    """Get the discovery service singleton."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = DiscoveryService(port=port)
    return _discovery_service


# FastAPI integration
async def start_discovery_on_startup():
    """Start mDNS discovery when the server starts."""
    service = get_discovery_service()
    await service.start()


async def stop_discovery_on_shutdown():
    """Stop mDNS discovery when the server shuts down."""
    service = get_discovery_service()
    await service.stop()
