"""Deprecated compatibility package for the previous generic src path."""

from __future__ import annotations

import importlib

_nxctl = importlib.import_module("nxctl")
__path__ = _nxctl.__path__


def __getattr__(name: str):
    return getattr(_nxctl, name)
