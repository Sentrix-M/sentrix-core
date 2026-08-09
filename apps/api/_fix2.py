"""One-off fix for WAZUH_MARKERS indentation in tool_integration.py."""

from pathlib import Path

p = Path("app/kernel/tool_integration.py")
s = p.read_text(encoding="utf-8")

old = """if any(marker in lower for marker in self.WAZUH_MARKERS):
            return ToolDecision("""

new = """        if any(marker in lower for marker in self.WAZUH_MARKERS):
            return ToolDecision("""

assert old in s, "WAZUH_MARKERS block not found"
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("FIXED2")
