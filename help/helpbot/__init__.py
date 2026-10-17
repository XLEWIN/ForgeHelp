"""Forge Help Bot — an AI assistant that only knows the Forge bot.

The package never imports ``forge`` (importing that package connects to
MongoDB, starts a Pyrogram client and reads the production token). It
reads the generated knowledge base and talks to an OpenAI-compatible
chat completion API instead.
"""

__all__ = ["config", "kb", "ai", "bot"]
