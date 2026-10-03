"""Duplicate detection and merging — Member 3 (§7, §23.2).

    from nexa.dedup import DuplicateService, merge

`compare` recommends; `merge` performs what the admin confirmed. The two are
deliberately separate, because Section 7 ends "Never silently delete uncertain
information" and gives the Review screen `[ Keep Both ]` / `[ Merge ]`.
"""

from .merge import EVIDENCE_SEPARATOR, merge, merge_all
from .merge_advisor import MergeAdvisor
from .service import DuplicateService
from .similarity import lexical_similarity, normalize_text

__all__ = [
    "DuplicateService",
    "EVIDENCE_SEPARATOR",
    "MergeAdvisor",
    "lexical_similarity",
    "merge",
    "merge_all",
    "normalize_text",
]
