import pytest
from riva_agent.intelligence.memory_router import MemoryRouter, AgentMemoryEvent

@pytest.fixture(scope="module")
def router():
    return MemoryRouter()

@pytest.mark.parametrize("query, expected_extract, expected_explicit", [
    # Explicit Directives
    ("Remember that my favorite color is blue", True, True),
    ("Please keep in mind that I am allergic to nuts", True, True),
    ("Forget my old home address", True, True),

    # Durable Profile Facts
    ("I work as a software engineer at Google", True, False),
    ("My daughter goes to elementary school", True, False),
    ("I live in New York City", True, False),
    ("I have a peanut allergy", True, False),

    # Transient Noise (Should be False)
    ("I had a sandwich for lunch", False, False),
    ("I am feeling a bit tired today", False, False),
    ("I'm just heading to the gym", False, False),
    ("I have a mild headache right now", False, False),

    # General Bypasses / Questions
    ("What is the capital of France?", False, False),
    ("How do I implement a binary search in Python?", False, False),
    ("Hi, how are you doing today?", False, False),
    ("Can you tell me a joke?", False, False),
    ("Elon Musk is the CEO of Tesla", False, False),

    # Edge Cases
    ("", False, False),
    ("   ", False, False),
])
def test_memory_router_logic(router, query, expected_extract, expected_explicit):
    event = router.route(query)
    assert isinstance(event, AgentMemoryEvent)
    assert event.should_extract_memory == expected_extract
    assert event.is_explicit == expected_explicit

def test_latency_is_recorded(router):
    event = router.route("I work at Google")
    assert event.latency_ms >= 0


def test_memory_router_helpers():
    from riva_agent.intelligence.memory_router import get_memory_router, route_memory

    router = get_memory_router()
    assert isinstance(router, MemoryRouter)

    event = route_memory("Remember to buy milk")
    assert isinstance(event, AgentMemoryEvent)
    assert event.is_explicit is True
    assert event.should_extract_memory is True
