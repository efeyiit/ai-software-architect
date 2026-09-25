"""Conservative, source-linked dependency graph over parser results."""

from .graph import DependencyEdge, DependencyGraph, DependencyNode, analyze_dependencies

__all__ = ["DependencyEdge", "DependencyGraph", "DependencyNode", "analyze_dependencies"]
