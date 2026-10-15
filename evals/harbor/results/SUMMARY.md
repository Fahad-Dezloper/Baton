# Evaluation summary

| Level | Arm | Trials | Clash-free | Avg failed checks | Collision warnings delivered | Most common problems |
|---|---|---|---|---|---|---|
| L1 | baseline | 5 | 4/5 | 0.2 | n/a | lost_update x1 |
| L1 | plugin | 5 | 4/5 | 0.2 | 4 | lost_update x1 |
| L2 | baseline | 5 | 5/5 | 0.0 | n/a | none |
| L2 | plugin | 5 | 4/5 | 0.2 | 3 | persistence_or_integration_gap x1 |
| L3 | baseline | 5 | 1/5 | 0.8 | n/a | contract_mismatch x4 |
| L3 | plugin | 5 | 0/5 | 1.0 | 4 | contract_mismatch x4, integration_break x1 |
| L4 | baseline | 5 | 2/5 | 1.2 | n/a | test_failure x3, config_conflict x2, stale_reference x1 |
| L4 | plugin | 5 | 1/5 | 0.8 | 7 | config_conflict x1, test_failure x1, lost_update x1 |
| L5 | baseline | 5 | 0/5 | 3.6 | n/a | requirement_unmet_F x4, orphaned_work x3, duplicate_work x3 |
| L5 | plugin | 5 | 0/5 | 3.0 | 26 | duplicate_work x4, requirement_unmet_E x4, orphaned_work x3 |
