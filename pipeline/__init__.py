"""Michigan Deal Radar data pipeline.

Pulls Michigan-related deal activity from SEC EDGAR (Form D, 8-K, Schedule 13D),
normalizes it into a single deal schema, and writes static JSON for the web app.
No AI/LLM calls anywhere: every classification and summary is rule-based.
"""

__version__ = "1.0.0"
