import pytest
from unittest.mock import MagicMock, patch
from riva_agent.intelligence.reasoning import ThinkingRouter, ReasoningEffort, HybridDecision

@pytest.fixture
def mock_spacy():
    with patch("spacy.load") as mock_load:
        mock_nlp = MagicMock()
        # Mock a doc object that returns lemmas and text
        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = [
            MagicMock(lemma_="hello", text="Hello"),
            MagicMock(lemma_="world", text="world")
        ]
        mock_nlp.return_value = mock_doc
        mock_load.return_value = mock_nlp
        yield mock_load

@pytest.fixture
def mock_laya():
    with patch("laya_mlx.load") as mock_load:
        mock_agent = MagicMock()
        # Mock predict to return a response with probabilities
        mock_agent.predict.return_value = {
            "answers": {
                "complexity": {
                    "probabilities": {"none": 0.6, "low": 0.2, "high": 0.2}
                }
            }
        }
        mock_load.return_value = mock_agent
        yield mock_load

def test_router_social_fast_path(mock_spacy, mock_laya):
    router = ThinkingRouter()
    decision = router.route("Hi there!")
    assert decision.requires_thinking is False
    assert decision.effort_level == ReasoningEffort.NONE
    assert "stage1_social_fast_path" in decision.source

def test_router_lookup_filter(mock_spacy, mock_laya):
    router = ThinkingRouter()
    decision = router.route("What is the capital of France?")
    assert decision.requires_thinking is False
    assert decision.effort_level == ReasoningEffort.NONE
    assert "stage1_lookup_explanation_filter" in decision.source

def test_router_transform_filter(mock_spacy, mock_laya):
    router = ThinkingRouter()
    decision = router.route("Translate hello to Spanish")
    assert decision.requires_thinking is False
    assert decision.effort_level == ReasoningEffort.NONE
    assert "stage1_transform_filter" in decision.source

def test_router_math_logic_detector(mock_spacy, mock_laya):
    router = ThinkingRouter()
    # Note: In the actual code, 'solve' needs to be in lemmas for this to trigger
    # We mock the spacy doc for this specific call on the router instance
    with patch.object(router, "nlp") as mock_nlp:
        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = [MagicMock(lemma_="solve", text="solve"), MagicMock(lemma_="x", text="x")]
        mock_nlp.return_value = mock_doc

        decision = router.route("Solve x > 5")
        assert decision.requires_thinking is True
        assert decision.effort_level == ReasoningEffort.HIGH
        assert "stage2_math_logic_detector" in decision.source

def test_router_laya_semantic(mock_spacy, mock_laya):
    router = ThinkingRouter()
    # We need a query that passes stage 1 and 2
    # And we want to test the Laya fallback
    with patch.object(router, "agent") as mock_agent:
        mock_agent.predict.return_value = {
            "answers": {
                "complexity": {
                    "probabilities": {"none": 0.1, "low": 0.1, "high": 0.6}
                }
            }
        }
        decision = router.route("Explain the quantum entanglement in detail")
        assert decision.requires_thinking is True
        assert decision.effort_level == ReasoningEffort.HIGH
        assert "stage3_laya_semantic" in decision.source

def test_route_messages(mock_spacy, mock_laya):
    router = ThinkingRouter()
    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hi!"}
    ]
    decision = router.route_messages(messages)
    assert decision.query == "Hi!"
    assert decision.requires_thinking is False

def test_route_messages_multimodal(mock_spacy, mock_laya):
    router = ThinkingRouter()
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "What is "},
            {"type": "text", "text": "this?"}
        ]}
    ]
    decision = router.route_messages(messages)
    assert decision.query == "What is this?"

def test_thinking_router_helpers(mock_spacy, mock_laya):
    from riva_agent.intelligence.reasoning import (
        get_thinking_router,
        decide_reasoning_effort,
        should_use_extended_thinking,
    )

    router = get_thinking_router()
    assert isinstance(router, ThinkingRouter)

    decision_str = decide_reasoning_effort("Hi!")
    assert decision_str.requires_thinking is False

    decision_msgs = decide_reasoning_effort([{"role": "user", "content": "Hi!"}])
    assert decision_msgs.requires_thinking is False

    assert should_use_extended_thinking("Hi!") is False

