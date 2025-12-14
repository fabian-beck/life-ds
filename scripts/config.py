#!/usr/bin/env python3
"""Shared configuration for generation scripts."""

import os

# OpenAI API configuration
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")
DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "medium")
LOW_REASONING_EFFORT = os.getenv("OPENAI_LOW_REASONING_EFFORT", "none")
