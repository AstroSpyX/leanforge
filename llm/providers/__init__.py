"""Provider adapters. One module per upstream API (anthropic, google).

The dispatcher in `llm.ask` picks the adapter based on
`ModelConfig.provider`. Adapters expose a single `call(...)` entry
point with the same signature; they own SDK-specific quirks (error
mapping, tool-format translation, system-prompt placement).
"""
