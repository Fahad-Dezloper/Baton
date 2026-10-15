"""Hook configuration (Phase 3.6): file `.baton.json` in the project, overridden by environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

POLICIES = ("warn", "ask", "deny")


@dataclass
class Config:
    enabled: bool = True
    policy: str = "warn"          # warn: inject context | ask: prompt the user | deny: block the call
    lease_seconds: int = 900


def load_config(project_dir: Optional[str]) -> Config:
    cfg = Config()
    if project_dir:
        path = os.path.join(project_dir, ".baton.json")
        try:
            with open(path) as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                cfg.enabled = bool(raw.get("enabled", cfg.enabled))
                cfg.policy = str(raw.get("policy", cfg.policy))
                cfg.lease_seconds = int(raw.get("lease_seconds", cfg.lease_seconds))
        except (OSError, ValueError):
            pass
    if os.environ.get("BATON_DISABLED", "").lower() in ("1", "true", "yes"):
        cfg.enabled = False
    cfg.policy = os.environ.get("BATON_POLICY", cfg.policy)
    if os.environ.get("BATON_LEASE_SECONDS", "").isdigit():
        cfg.lease_seconds = int(os.environ["BATON_LEASE_SECONDS"])
    if cfg.policy not in POLICIES:
        cfg.policy = "warn"
    cfg.lease_seconds = max(60, min(cfg.lease_seconds, 6 * 3600))
    return cfg
