"""供应商配置测试替身，隔离真实项目 .env 与进程环境变量。"""
from contextlib import contextmanager
from unittest.mock import patch

@contextmanager
def config_fixture(values, clear=False):
    def value(key):
        return values.get(key)
    with patch('providers.config_value', side_effect=value), patch('providers.transport.config_value', side_effect=value), patch('core.jobs.config_value', side_effect=value):
        yield
