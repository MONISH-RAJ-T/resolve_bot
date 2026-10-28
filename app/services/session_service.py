"""Chat sessions: history and the one waiting proposal, kept by session_id.
A session belongs to the customer who started it."""
import re
import threading


class Session:
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.history: list[dict] = []   # [{"role": "user" | "assistant", "content": str}]
        self.pending: dict | None = None  # the waiting proposal: {"name": ..., "args": {...}}
        self.lock = threading.Lock()


_sessions: dict[str, Session] = {}
_store_lock = threading.Lock()


def session_owner(session_id: str) -> str | None:
    with _store_lock:
        s = _sessions.get(session_id)
        return s.customer_id if s else None


def get_session(session_id: str, customer_id: str) -> Session:
    """Creates the session if new. Raises PermissionError if it belongs to another customer."""
    with _store_lock:
        s = _sessions.get(session_id)
        if s is None:
            s = _sessions[session_id] = Session(customer_id)
        elif s.customer_id != customer_id:
            raise PermissionError("session belongs to another customer")
        return s


_YES_WORDS = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "proceed", "y",
              "go", "ahead", "please", "do", "it", "thanks", "thank", "you"}
_YES_CORE = re.compile(r"\b(yes|yeah|yep|yup|sure|ok|okay|confirm|confirmed|proceed|y)\b|go ahead|please do")


def is_yes(message: str) -> bool:
    """A clear yes only: short, made of yes-words, and containing a real yes.
    'just do it' and 'yes but only the power bank' are NOT a yes."""
    words = re.findall(r"[a-z']+", message.lower())
    if not words or len(words) > 6 or any(w not in _YES_WORDS for w in words):
        return False
    return bool(_YES_CORE.search(" ".join(words)))
