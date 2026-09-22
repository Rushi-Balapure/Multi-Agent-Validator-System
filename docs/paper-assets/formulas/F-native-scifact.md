# F-native-scifact — Native SciFact scores

**Plan cite:** Research plan §11 Verification quality.  
**Every table cell using this metric must cite `run_id` + this formula id.**

## Definition

Official SciFact support / refute / evidence metrics via the community evaluation adapters on the public benchmark split. Keep official three-way labels distinct from custom four-way labels.

## Notes

Three-way insufficient-information labels do not supply gold four-way underdetermined labels. A supplementary coarse mapping (collapse unaddressed + underdetermined → insufficient information) must be labeled as supplementary, never as native.
