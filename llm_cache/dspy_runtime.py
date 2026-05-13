"""Compatibility shim – all symbols now live under runtime.agent.*."""
from __future__ import annotations

from runtime.agent.callbacks import DspyWandbCallback as DspyWandbCallback
from runtime.agent.dspy_agent import (
    BespokeAgentSignature as BespokeAgentSignature,
    ConversationSummary as ConversationSummary,
    DspyBespokeAgent as DspyBespokeAgent,
    DspyCacheEntry as DspyCacheEntry,
    RLM_INSTRUCTOR_SIGNATURE as RLM_INSTRUCTOR_SIGNATURE,
)
from runtime.agent.session_store import DspySessionStore as DspySessionStore
from runtime.agent.toolbox import DspyToolbox as DspyToolbox

__all__ = [
    "BespokeAgentSignature",
    "ConversationSummary",
    "DspyBespokeAgent",
    "DspyCacheEntry",
    "DspySessionStore",
    "DspyToolbox",
    "DspyWandbCallback",
    "RLM_INSTRUCTOR_SIGNATURE",
]
