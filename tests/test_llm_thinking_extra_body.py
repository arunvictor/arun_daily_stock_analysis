# -*- coding: utf-8 -*-
"""Focused tests for provider-scoped thinking extra_body resolution."""

from __future__ import annotations

import unittest

from src.agent.llm_adapter import get_thinking_extra_body


class GetThinkingExtraBodyTest(unittest.TestCase):
    def test_ollama_qwen3_disables_thinking(self) -> None:
        """Ollama Qwen3 requests should pass think=False to skip the default thinking pass."""
        self.assertEqual(
            get_thinking_extra_body("ollama/qwen3:4b"),
            {"think": False},
        )

    def test_ollama_qwen3_without_version_tag_disables_thinking(self) -> None:
        self.assertEqual(
            get_thinking_extra_body("ollama/qwen3"),
            {"think": False},
        )

    def test_non_ollama_qwen3_preserves_existing_behavior(self) -> None:
        """Qwen3 on a non-Ollama backend must not receive the Ollama think flag."""
        self.assertIsNone(get_thinking_extra_body("openai/qwen3:4b"))
        self.assertIsNone(get_thinking_extra_body("qwen3:4b"))

    def test_deepseek_opt_in_thinking_unchanged(self) -> None:
        """DeepSeek opt-in behavior must be preserved regardless of provider prefix."""
        self.assertEqual(
            get_thinking_extra_body("deepseek-chat"),
            {"thinking": {"type": "enabled"}},
        )
        self.assertEqual(
            get_thinking_extra_body("openai/deepseek-chat"),
            {"thinking": {"type": "enabled"}},
        )

    def test_auto_thinking_model_returns_none(self) -> None:
        """Auto-thinking models must not receive an extra_body activation payload."""
        self.assertIsNone(get_thinking_extra_body("deepseek-reasoner"))


if __name__ == "__main__":
    unittest.main()