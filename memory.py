"""LangGraph MemorySaver for bounded, per-session short-term conversation memory."""
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver

short_term_memory = MemorySaver()


def load_history(session_id) -> list[dict]:
    checkpoint = short_term_memory.get({"configurable": {"thread_id": str(session_id)}})
    return checkpoint["channel_values"].get("messages", []) if checkpoint else []


def forget(session_id) -> None:
    short_term_memory.delete_thread(str(session_id))


def save_history(session_id, messages: list[dict]) -> None:
    # Keep only the latest checkpoint, not an ever-growing checkpoint history.
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": messages[-12:]}
    checkpoint["channel_versions"] = {"messages": 1}
    forget(session_id)
    short_term_memory.put(
        {"configurable": {"thread_id": str(session_id), "checkpoint_ns": ""}},
        checkpoint, {"source": "update", "step": 0, "parents": {}}, {"messages": 1},
    )
