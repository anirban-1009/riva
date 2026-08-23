import json
import uuid
from pathlib import Path
from typing import Any

from job_genie.utils.logger import get_logger

logger = get_logger(__name__)


class CanvasManager:
    """Manages the creation and export of Obsidian Canvas files."""

    def __init__(self):
        """Initialize the CanvasManager."""
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []

    def add_node(
        self,
        node_type: str,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str | None = None,
        file_path: str | None = None,
        color: str | None = None,
        label: str | None = None,
    ) -> str:
        """Add a node to the canvas.

        Args:
            node_type: 'text', 'file', 'link', or 'group'.
            x: X coordinate.
            y: Y coordinate.
            width: Node width.
            height: Node height.
            text: Content for 'text' or 'group' nodes.
            file_path: Path for 'file' nodes (relative to vault).
            color: Color code (1-6) or hex.
            label: Optional label for group nodes (if different from text).

        Returns:
            The unique ID of the created node.
        """
        node_id = str(uuid.uuid4())
        node = {
            "id": node_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "type": node_type,
        }

        if node_type == "text" and text:
            node["text"] = text
        elif node_type == "file" and file_path:
            node["file"] = file_path
        elif node_type == "group" and label:
            node["label"] = label

        if color:
            node["color"] = color

        self.nodes.append(node)
        return node_id

    def add_edge(
        self,
        from_node: str,
        from_side: str,
        to_node: str,
        to_side: str,
        color: str | None = None,
        label: str | None = None,
    ) -> str:
        """Add a directional edge between two nodes.

        Args:
            from_node: Source node ID.
            from_side: 'top', 'right', 'bottom', 'left'.
            to_node: Target node ID.
            to_side: 'top', 'right', 'bottom', 'left'.
            color: Optional color.
            label: Optional label for the edge.

        Returns:
            The unique ID of the created edge.
        """
        edge_id = str(uuid.uuid4())
        edge = {
            "id": edge_id,
            "fromNode": from_node,
            "fromSide": from_side,
            "toNode": to_node,
            "toSide": to_side,
        }

        if color:
            edge["color"] = color
        if label:
            edge["label"] = label

        self.edges.append(edge)
        return edge_id

    def generate_json(self) -> str:
        """Generate the JSON string for the canvas."""
        canvas_data = {"nodes": self.nodes, "edges": self.edges}
        return json.dumps(canvas_data, indent=4)

    def save_to_file(self, file_path: Path):
        """Save the canvas JSON to a file."""
        content = self.generate_json()
        logger.info(f"Saving canvas to {file_path}")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
