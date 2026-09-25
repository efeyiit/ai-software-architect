"""Static test discovery and separately sourced coverage evidence."""

from .analyzer import analyze_testing, TestingReport, parse_coverage_xml

__all__ = ["analyze_testing", "TestingReport", "parse_coverage_xml"]
