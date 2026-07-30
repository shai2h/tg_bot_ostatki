import asyncio
from monitoring.monitoring import SystemMonitor

if __name__ == "__main__":
    monitor = SystemMonitor()
    asyncio.run(monitor.start_monitoring())