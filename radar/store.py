"""Persistent memory of everything we have already seen."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta

from .util import Opportunity

DEFAULT_PATH = os.path.join("data", "seen.json")


class Store:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        try:
            with open(path, encoding="utf-8") as fh:
                self.data: dict[str, dict] = json.load(fh)
        except Exception:                      # noqa: BLE001
            self.data = {}

    def mark(self, ops: list[Opportunity]) -> list[Opportunity]:
        """Fill `first_seen`; return only the ones never seen before."""
        today = date.today().isoformat()
        new: list[Opportunity] = []
        for op in ops:
            rec = self.data.get(op.uid)
            if rec:
                op.first_seen = rec.get("first_seen", today)
            else:
                op.first_seen = today
                self.data[op.uid] = {"first_seen": today, "title": op.title, "url": op.url}
                new.append(op)
        return new

    def prune(self, days: int = 400) -> None:
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        self.data = {k: v for k, v in self.data.items() if v.get("first_seen", "9999") >= cutoff}

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=1, sort_keys=True)
