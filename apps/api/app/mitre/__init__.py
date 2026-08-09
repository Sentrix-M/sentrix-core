"""Sentrix MITRE ATT&CK mapping engine.

Maps findings from security tools (Nmap, VirusTotal, Shodan) into MITRE
ATT&CK techniques and tactics using a local, offline knowledge base. The
mapping is exposed to the AI layer (kernel/prompt) so the provider can
explain why each technique applies and recommend mitigations.

Public API
----------
- :class:`~app.mitre.mapper.MitreMapper` — ``map(tool_result) -> MitreMapping``
- :class:`~app.mitre.models.MitreMapping` / :class:`~app.mitre.models.MitreTechnique`
- :class:`~app.mitre.knowledge_base.MitreKnowledgeBase` — extensible local KB
- :func:`~app.mitre.integration.enrich_tool_result` — serialized mapping helper
"""

from app.mitre.integration import enrich_tool_result
from app.mitre.knowledge_base import ATTACK_VERSION, MitreKnowledgeBase, TechniqueEntry
from app.mitre.mapper import MitreMapper
from app.mitre.models import MitreMapping, MitreTechnique

__all__ = [
    "ATTACK_VERSION",
    "MitreKnowledgeBase",
    "MitreMapper",
    "MitreMapping",
    "MitreTechnique",
    "TechniqueEntry",
    "enrich_tool_result",
]
