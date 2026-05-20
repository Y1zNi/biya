"""平台采集器注册."""

from infra.collectors.registry import COLLECTOR_MAP, get_collector

__all__ = ['COLLECTOR_MAP', 'get_collector']
