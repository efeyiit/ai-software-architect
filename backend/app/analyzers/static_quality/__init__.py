"""Source-linked static quality checks over inert parser results and source text."""

from .analyzer import QualityThresholds, analyze_static_quality

__all__ = ["QualityThresholds", "analyze_static_quality"]
