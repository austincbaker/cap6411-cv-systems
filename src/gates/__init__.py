"""Cheap change gate that decides when a frame is worth a VLM call (item 2a)."""

from gates.change import ChangeGate, GateConfig, GateDecision, change_score, preprocess

__all__ = ["ChangeGate", "GateConfig", "GateDecision", "change_score", "preprocess"]
