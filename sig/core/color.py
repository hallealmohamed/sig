"""Advanced color management for tactical visualization."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass
class LayerDescriptor:
    name: str
    semantic: str
    importance: float = 0.5


class IntelligentColorEngine:
    """Assign colors based on semantics and operational context."""

    _CONTEXT_BASES: Dict[str, List[str]] = {
        "tactical": ["#2E8BC0", "#145DA0", "#0C2D48", "#B1D4E0"],
        "night": ["#0b0c10", "#1f2833", "#c5c6c7", "#66fcf1"],
        "infrared": ["#330000", "#ff4500", "#ffd700", "#ffffff"],
    }

    def assign_optimal_colors(self, layers: Iterable[LayerDescriptor], context: str = "tactical") -> Dict[str, str]:
        palette = self._CONTEXT_BASES.get(context, self._CONTEXT_BASES["tactical"])
        sorted_layers = sorted(layers, key=lambda layer: layer.importance, reverse=True)
        assignments: Dict[str, str] = {}
        for index, layer in enumerate(sorted_layers):
            color = palette[index % len(palette)]
            if layer.semantic == "threat":
                color = "#ff4d4f"
            elif layer.semantic == "ally":
                color = "#52c41a"
            assignments[layer.name] = color
        return assignments
