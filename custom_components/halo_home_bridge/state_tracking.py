"""Reconcile asynchronous bridge commands with stale cloud snapshots."""
from datetime import datetime
import time

FIELDS = {"white": "kelvin", "dim": "brightness", "on_off": "on"}


def version(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return None


def command_value(feature, value):
    if feature == "white":
        return int(value)
    if feature == "dim":
        text = str(value)
        return round(float(text[:-1]) * 255 / 100) if text.endswith("%") else int(text)
    if feature == "on_off":
        return str(value).lower() in {"on", "1"}
    return None


class StateTracker:
    """Accepted values are estimates until a subsequent cloud read confirms them."""
    def __init__(self, clock=time.monotonic, timeout=30):
        self.clock = clock
        self.timeout = timeout
        self.observed = {}
        self.pending = {}
        self.outcomes = {}
        self.reads = {}

    def accept(self, key, feature, value):
        field = FIELDS.get(feature)
        if field is None:
            return
        desired = command_value(feature, value)
        token = (key, field)
        baseline = self.observed.get(token, (None, None))
        if token not in self.pending and baseline[0] == desired:
            return
        self.pending[token] = {"desired": desired, "baseline": baseline,
                               "issued": self.clock()}
        self.outcomes[token] = "pending"

    def reconcile(self, key, state, versions=None, read_started=None):
        result = dict(state)
        versions = versions or {}
        now = self.clock()
        for field in ("on", "brightness", "kelvin"):
            token = (key, field)
            raw = state.get(field)
            stamp = version(versions.get(field))
            previous = self.observed.get(token)
            older_request = (read_started is not None and read_started < self.reads.get(token, float('-inf')))
            older = older_request or (previous is not None and previous[1] is not None
                     and (stamp is None or stamp < previous[1]))
            if older:
                if previous is not None:
                    raw, stamp = previous
            elif read_started is not None:
                self.observed[token] = (raw, stamp)
                self.reads[token] = read_started
            elif previous is not None:
                # Re-rendering an estimate must never turn it into an observation.
                raw, stamp = previous
            result[field] = raw
            pending = self.pending.get(token)
            if pending is None:
                continue
            baseline_value, baseline_stamp = pending["baseline"]
            fresh_read = read_started is not None and read_started >= pending["issued"]
            advanced = (stamp is not None and baseline_stamp is not None and stamp > baseline_stamp)
            changed = raw != baseline_value
            if fresh_read and not older and raw == pending["desired"] and (advanced or changed or baseline_stamp is None):
                del self.pending[token]
                self.outcomes[token] = "confirmed"
            elif now - pending["issued"] >= self.timeout:
                del self.pending[token]
                self.outcomes[token] = "not_confirmed"
            else:
                result[field] = pending["desired"]
        return result

    def attributes(self, key):
        fields = [field for (target, field) in self.pending if target == key]
        outcomes = {field: status for (target, field), status in self.outcomes.items() if target == key}
        return {"state_source": "accepted command pending cloud readback" if fields else "cloud",
                "pending_confirmation": fields, "command_readback": outcomes}

    def has_pending(self, keys):
        return any(key in keys for key, field in self.pending)

    def fail(self, key):
        for token in list(self.pending):
            if token[0] == key:
                del self.pending[token]
                self.outcomes[token] = "not_confirmed"
