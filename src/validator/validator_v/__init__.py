"""Stack V batch runner.

See ``validator.validator_v.labels`` for the four-way → SUPPORT/REFUTE/NEI
mapping and ``validator.validator_v.runner`` for the CLI. Gather D0 citations
come from ``validator.validator_v.cited_d0`` (non-gold ``cited_doc_ids``).
"""

from validator.validator_v.labels import FOUR_WAY_TO_NATIVE, map_four_way_label
from validator.validator_v.runner import PHASE3_B2_CLAIM_IDS

__all__ = ["FOUR_WAY_TO_NATIVE", "PHASE3_B2_CLAIM_IDS", "map_four_way_label"]
