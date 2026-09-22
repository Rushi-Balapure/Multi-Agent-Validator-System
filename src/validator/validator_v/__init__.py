"""Stack V batch runner.

See ``validator.validator_v.labels`` for the four-way → SUPPORT/REFUTE/NEI
mapping and ``validator.validator_v.runner`` for the CLI.
"""

from validator.validator_v.labels import FOUR_WAY_TO_NATIVE, map_four_way_label

__all__ = ["FOUR_WAY_TO_NATIVE", "map_four_way_label"]
