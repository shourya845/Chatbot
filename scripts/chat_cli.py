"""Run terminal chat with: python -m scripts.chat_cli [--debug]."""
import asyncio
import logging
import sys
from uuid import uuid4

import httpx

from app.agent import MODEL, stream_chat
from app.memory import load_history, save_history


async def main():
    session_id = uuid4()
    print("a31-assistance | type bye to exit.", flush=True)
    while True:
        try:
            message = input("You: ").strip()
            if message.lower() in {"bye", "/bye", "exit"}:
                break
            if not message:
                continue
            print("Thinking...", flush=True)
            history = load_history(session_id)
            chunks = []
            started = False
            async for delta in stream_chat(message, history):
                if not started:
                    print("a31-assistance: ", end="", flush=True)
                    started = True
                print(delta, end="", flush=True)
                chunks.append(delta)
            print(flush=True)
            answer = "".join(chunks)
            save_history(session_id, history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": answer},
            ])
        except (EOFError, KeyboardInterrupt):
            break
        except httpx.ConnectError:
            print(
                "Cannot connect to Ollama. Start the Ollama app or run: ollama serve",
                flush=True,
            )
        except httpx.TimeoutException:
            print("Ollama took too long. Close memory-heavy apps and try again.", flush=True)
        except ValueError:
            print(
                "\nSearch or answer generation failed. "
                "Check your search configuration and retry.",
                flush=True,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                print(f"Model not found. Run: ollama pull {MODEL}", flush=True)
            else:
                print(
                    f"Ollama returned HTTP {exc.response.status_code}. "
                    "Check the Ollama server.",
                    flush=True,
                )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--debug" in sys.argv:
        logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
        logging.getLogger("app.agent").setLevel(logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

