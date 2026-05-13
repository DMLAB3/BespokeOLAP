import os
from typing import Any

import dspy

DEFAULT_DSPY_MODEL = "gemini/gemini-3.1-flash-lite"
DEFAULT_DSPY_INSTRUCTOR_MODEL = "gemini/gemini-3-pro-preview"


def setup_dspy_model_config(
    model_arg: str | None = None,
    callbacks: list[Any] | None = None,
) -> tuple[str, dspy.LM]:
    model_name = model_arg or DEFAULT_DSPY_MODEL
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be set for DSPy Gemini models.")

    lm = dspy.LM(model_name, api_key=api_key, cache=True)
    dspy.configure(lm=lm, track_usage=True, callbacks=callbacks or [])
    return model_name, lm


def setup_dspy_instructor_model_config(
    model_arg: str | None = None,
) -> tuple[str, dspy.LM]:
    model_name = model_arg or DEFAULT_DSPY_INSTRUCTOR_MODEL
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY must be set for DSPy Gemini models.")

    lm = dspy.LM(model_name, api_key=api_key, cache=True, temperature=0.7)
    return model_name, lm
