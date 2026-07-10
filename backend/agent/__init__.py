"""
DRIVEWISE — Natural Language Query Agent
Flow:
1. NL Question → LLM (Claude 3.5 Sonnet) → SQL query + Chart suggestion
2. SQL validation & execution (with automatic self-correction)
3. SQL Result + NL Question → LLM → Natural Language Answer
"""
