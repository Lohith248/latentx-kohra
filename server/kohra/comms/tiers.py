"""Precedence tiers (D31): FLASH > IMMEDIATE > PRIORITY > ROUTINE."""

from __future__ import annotations

PRECEDENCE_RANK = {"FLASH": 0, "IMMEDIATE": 1, "PRIORITY": 2, "ROUTINE": 3}
DEFAULT_PRECEDENCE = "PRIORITY"

# Default precedence for scripted traffic by message type.
TEMPLATE_PRECEDENCE = {
    "contact": "IMMEDIATE",
    "locstat": "ROUTINE",
    "sitrep": "PRIORITY",
    "ack": "PRIORITY",
    "say_again": "PRIORITY",
    "fire_status": "PRIORITY",
}
