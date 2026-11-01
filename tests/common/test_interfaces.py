"""Tests for common.interfaces.plugin module."""

from common.interfaces.plugin import GenieCoordinator, PluginContext


def test_plugin_context_creation():
    ctx = PluginContext(domain="lighthouse", facts=["Fact 1"])
    assert ctx.domain == "lighthouse"
    assert ctx.facts == ["Fact 1"]
    assert ctx.data == {}


def test_genie_coordinator_protocol():
    class DummyCoordinator:
        name = "dummy"

        async def initialize(self) -> None:
            pass

        async def gather_context(self, **kwargs) -> dict:
            return {"status": "ok"}

    dummy = DummyCoordinator()
    assert isinstance(dummy, GenieCoordinator)
