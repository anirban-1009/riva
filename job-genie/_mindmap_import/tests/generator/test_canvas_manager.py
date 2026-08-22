import json

from src.generator.canvas_manager import CanvasManager


def test_add_node_returns_unique_ids():
    manager = CanvasManager()
    id1 = manager.add_node(node_type="text", x=0, y=0, width=100, height=50, text="Hello")
    id2 = manager.add_node(node_type="text", x=100, y=0, width=100, height=50, text="World")

    assert id1 != id2
    assert len(manager.nodes) == 2
    assert manager.nodes[0]["text"] == "Hello"
    assert "color" not in manager.nodes[0]


def test_add_node_with_color():
    manager = CanvasManager()
    manager.add_node(node_type="text", x=0, y=0, width=100, height=50, text="Bar", color="4")

    assert manager.nodes[0]["color"] == "4"


def test_add_edge():
    manager = CanvasManager()
    n1 = manager.add_node(node_type="text", x=0, y=0, width=100, height=50, text="A")
    n2 = manager.add_node(node_type="text", x=200, y=0, width=100, height=50, text="B")
    edge_id = manager.add_edge(n1, "right", n2, "left")

    assert len(manager.edges) == 1
    assert manager.edges[0]["id"] == edge_id
    assert manager.edges[0]["fromNode"] == n1
    assert manager.edges[0]["toNode"] == n2


def test_generate_json_roundtrips():
    manager = CanvasManager()
    manager.add_node(node_type="text", x=0, y=0, width=100, height=50, text="Node")
    data = json.loads(manager.generate_json())

    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 1


def test_save_to_file(tmp_path):
    manager = CanvasManager()
    manager.add_node(node_type="text", x=0, y=0, width=100, height=50, text="Node")
    out_path = tmp_path / "sub" / "Dashboard.canvas"

    manager.save_to_file(out_path)

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["nodes"]) == 1
