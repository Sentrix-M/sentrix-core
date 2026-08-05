"""One-off helper to normalize the markers block in tool_integration.py."""

from pathlib import Path

p = Path("app/kernel/tool_integration.py")
s = p.read_text(encoding="utf-8")

# Fix SHODAN_MARKERS block (currently unindented SHODAN_MARKERS line).
old = """    #: Message patterns that trigger the Shodan *internet-exposure* intent.
SHODAN_MARKERS: tuple[str, ...] = (
        "shodan",
        "internet exposure",
        "open ports",
        "port exposure",
        "exposed services",
    )"""

new = """    #: Message patterns that trigger the Shodan *internet-exposure* intent.
    SHODAN_MARKERS: tuple[str, ...] = (
        "shodan",
        "internet exposure",
        "open ports",
        "port exposure",
        "exposed services",
    )"""

assert old in s, "SHODAN_MARKERS block not found"
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("FIXED")
