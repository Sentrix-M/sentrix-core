"""One-off fix for the conversation_service indentation in main.py."""

from pathlib import Path

p = Path("app/main.py")
s = p.read_text(encoding="utf-8")

old = """app.state.conversation_service = ConversationService()

    # RAG document ingestion engine"""

new = """    app.state.conversation_service = ConversationService()

    # RAG document ingestion engine"""

assert old in s, "conversation_service block not found"
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("FIXED3")
