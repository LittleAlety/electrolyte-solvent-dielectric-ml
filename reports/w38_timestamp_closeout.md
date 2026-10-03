# W38-E 收口：干净重导不再把工作树写脏（后验，不占 shot）

README §11 第 19 条登记：被跟踪的 summary 带 `generated_at_utc` / `elapsed_seconds`，
重跑写入器就会脏树，而 `worktree_dirty` 与 `artifacts_commit` 是 AF-12 标识交付字节的坐标。

## 1. 修法

`probes/export_results_common.write_json_stable(path, payload)`：写入前先与盘上文件比对，
**若除 volatile 键（`generated_at_utc` / `elapsed_seconds`）外完全一致，则保留原字节**；
否则照常写入。语义是「同一内容不重记时间」，不是「永不写」。

已接线：`probes/w37_gate_admission_export.py` 的 summary 写入由 `write_json_lf` 换成
`write_json_stable`。

## 2. 端到端证据

| 项 | 值 |
| --- | --- |
| 重跑前 `git status` 该文件 | 空 |
| 重跑次数 | 2 |
| 每次退出码 | 0, 0 |
| 每次写入器回报 | `summary unchanged`, `summary unchanged` |
| 重跑后 `git status` 该文件 | 空 |

## 3. 盘点（111 个带时间戳的被跟踪 JSON）

| 状态 | 数量 |
| --- | --- |
| 已迁移稳定写入 | 1 |
| 待迁移 | 110 |
| 无写入器（历史产物） | 0 |

待迁移清单（写入器仍在用普通写入）：

| 被跟踪 JSON | 写入器 |
| --- | --- |
| models/homo_lumo_baselines.json | probes/export_week13_results.py;probes/four_channel_coverage.py;probes/homo_lumo_baselines.py;probes/plot_week17_channels.py;probes/w19_ranking_key.py;probes/w20_ranking_key_v1.py;tests/test_export_week13_results.py;tests/test_w19_ranking_key.py |
| probes/artifacts/w33_bound_state_gate_summary.json | probes/export_week33_results.py;probes/export_week34_results.py;probes/w33_bound_state_gate.py;probes/w34_legality_registry.py |
| probes/artifacts/w33_kendall_null_summary.json | probes/export_week33_results.py;probes/w33_kendall_null_tool.py;tests/test_w33_kendall_null_tool.py |
| probes/artifacts/w34_legality_registry_summary.json | probes/export_week34_results.py;probes/export_week35_results.py;probes/w34_legality_registry.py;tests/test_w34_legality_registry.py |
| probes/artifacts/w34_paired_power_summary.json | probes/export_week34_results.py;probes/export_week35_results.py;probes/w34_paired_power.py;probes/w35_paper_r6_correction.py;tests/test_w34_paired_power.py;tests/test_w35_paper_r6_correction.py |
| probes/artifacts/w35_paper_r6_correction_summary.json | probes/export_week35_results.py;probes/w35_paper_r6_correction.py;tests/test_w35_paper_r6_correction.py |
| probes/artifacts/w35_redox_gate_consumers_summary.json | probes/export_week35_results.py;probes/w35_redox_gate_consumers.py;tests/test_w35_redox_gate_consumers.py |
| probes/artifacts/w36_channel_noise_floor_summary.json | probes/export_week36_results.py;probes/w36_channel_noise_floor.py;tests/test_w36_channel_noise_floor.py |
| probes/artifacts/w36_endpoint_rule_summary.json | probes/export_week36_results.py;probes/w36_endpoint_rule.py;tests/test_w36_endpoint_rule.py |
| probes/artifacts/w36_gate_admission_summary.json | probes/export_week36_results.py;probes/w36_gate_admission.py;tests/test_w36_gate_admission.py |
| probes/artifacts/w36_v2_source_correction_summary.json | probes/export_week36_results.py;probes/w36_v2_source_correction.py;tests/test_w36_v2_source_correction.py |
| probes/artifacts/w37_endpoint_tolerance_guard_summary.json | probes/export_week37_results.py;probes/w37_endpoint_tolerance_guard.py |
| probes/artifacts/w37_v2_backfill_summary.json | probes/export_week37_results.py;probes/w37_v2_backfill.py |
| probes/database_recheck.json | probes/export_week4_week5_results.py;scripts/audit_dielectric_databases.py |
| probes/density_v01_summary.json | probes/build_density_v01.py;probes/export_week17_results.py;probes/four_channel_coverage.py;tests/test_export_week17_results.py |
| probes/dielectric_anchor_build_summary.json | probes/build_dielectric_anchor_blocks.py;probes/export_week17_results.py |
| probes/dielectric_anchor_summary.json | probes/dielectric_anchor_benchmark.py;probes/export_week17_results.py;probes/plot_week17_pool_expansion.py;tests/test_dielectric_pool_expansion_v3.py |
| probes/dielectric_applicability_domain_summary.json | probes/dielectric_applicability_domain.py;probes/export_week18_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/plot_week18.py;probes/w20_funnel_kpi.py;probes/w20_ranking_key_v1.py;probes/w20_refusal.py |
| probes/dielectric_association_features_summary.json | probes/dielectric_association_features_probe.py;probes/dielectric_merge_arm_probe.py;probes/export_week14_results.py;tests/test_dielectric_association_features_probe.py;tests/test_export_week14_results.py |
| probes/dielectric_auc_sidecar_summary.json | probes/dielectric_auc_sidecar.py;probes/export_week17_results.py;tests/test_auc_sidecar_and_splitters.py |
| probes/dielectric_bagging_probe_summary.json | probes/dielectric_bagging_probe.py;probes/dielectric_merge_arm_probe.py;probes/export_week14_results.py;tests/test_dielectric_bagging_probe.py;tests/test_export_week14_results.py |
| probes/dielectric_channel_v2_summary.json | probes/dielectric_channel_v2.py;tests/test_dielectric_channel_v2.py;tests/test_l3_backvalidation_prereg.py |
| probes/dielectric_conformer_flexibility_placebo_summary.json | probes/dielectric_conformer_flexibility.py;probes/export_week18_results.py;probes/plot_week18.py;tests/test_conformer_flexibility.py |
| probes/dielectric_conformer_flexibility_summary.json | probes/dielectric_conformer_flexibility.py;probes/export_week18_results.py;probes/plot_week18.py;tests/test_conformer_flexibility.py |
| probes/dielectric_coordination_block_full_summary.json | probes/dielectric_coordination_block_full.py;probes/export_week17_results.py |
| probes/dielectric_coordination_block_summary.json | probes/dielectric_coordination_block.py;probes/dielectric_coordination_block_v2.py;probes/dielectric_coordination_block_v3.py;probes/export_week14_results.py;tests/test_dielectric_coordination_block_v2.py;tests/test_dielectric_coordination_block_v3.py;tests/test_export_week14_results.py |
| probes/dielectric_coordination_block_v2_summary.json | probes/dielectric_coordination_block_v2.py;probes/dielectric_coordination_block_v3.py;probes/export_week14_results.py;tests/test_export_week14_results.py |
| probes/dielectric_coordination_block_v3_summary.json | probes/dielectric_applicability_domain.py;probes/dielectric_coordination_block_v3.py;probes/export_week17_results.py;probes/export_week18_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/four_channel_coverage.py;tests/test_applicability_domain.py;tests/test_export_week17_results.py |
| probes/dielectric_head_sweep_summary.json | probes/dielectric_head_sweep.py;probes/export_week17_results.py;probes/export_week18_results.py;probes/plot_head_sweep.py;tests/test_head_sweep.py |
| probes/dielectric_hybrid_shap_summary.json | probes/dielectric_hybrid_shap.py;probes/export_week15_results.py;tests/test_export_week15_results.py |
| probes/dielectric_hyperparameter_grid_placebo_summary.json | probes/dielectric_hyperparameter_grid.py |
| probes/dielectric_hyperparameter_grid_summary.json | probes/dielectric_hyperparameter_grid.py;probes/export_week18_results.py;probes/plot_week18.py;tests/test_hyperparameter_grid.py |
| probes/dielectric_knowledge_purity_sweep_erratum_summary.json | probes/dielectric_knowledge_purity_sweep_erratum.py |
| probes/dielectric_knowledge_purity_sweep_summary.json | probes/dielectric_hybrid_shap.py;probes/dielectric_knowledge_purity_sweep.py;probes/dielectric_knowledge_purity_sweep_erratum.py;probes/export_week14_results.py;tests/test_dielectric_knowledge_purity_sweep_erratum.py;tests/test_export_week14_results.py |
| probes/dielectric_log_scale_calibration_placebo_summary.json | probes/dielectric_log_scale_calibration.py;tests/test_log_scale_calibration.py |
| probes/dielectric_log_scale_calibration_summary.json | probes/dielectric_log_scale_calibration.py;probes/export_week18_results.py;probes/plot_week18.py;tests/test_log_scale_calibration.py |
| probes/dielectric_merge_arm_summary.json | probes/dielectric_merge_arm_probe.py;probes/export_week14_results.py;tests/test_dielectric_merge_arm_probe.py;tests/test_export_week14_results.py |
| probes/dielectric_multiseed_endpoint_summary.json | probes/dielectric_multiseed_endpoint.py;probes/export_week18_results.py;probes/plot_week18.py |
| probes/dielectric_onsager_delta_w18_placebo_summary.json | probes/export_week18_results.py;tests/test_dielectric_onsager_delta_w18.py |
| probes/dielectric_onsager_delta_w18_summary.json | probes/dielectric_onsager_delta_w18.py;probes/export_week18_results.py;probes/plot_week18.py;tests/test_dielectric_onsager_delta_w18.py |
| probes/dielectric_pool_expansion_build_summary.json | probes/build_dielectric_pool_expansion.py;probes/export_week17_results.py |
| probes/dielectric_pool_expansion_full_table_summary.json | probes/dielectric_pool_expansion_full_table.py;probes/export_week17_results.py;probes/plot_week17_pool_expansion.py |
| probes/dielectric_pool_expansion_summary.json | probes/dielectric_pool_expansion_benchmark.py;probes/export_week17_results.py;probes/plot_week17_pool_expansion.py |
| probes/dielectric_pool_expansion_v3_summary.json | probes/dielectric_pool_expansion_v3.py;probes/export_week17_results.py;probes/plot_week17_pool_expansion.py;tests/test_dielectric_pool_expansion_v3.py |
| probes/dielectric_representation_seed_robustness_summary.json | probes/dielectric_representation_seed_robustness.py;probes/export_week17_results.py;probes/export_week18_results.py;probes/plot_representation_seed_robustness.py;tests/test_representation_seed_robustness.py |
| probes/dielectric_split_conformal_summary.json | probes/dielectric_split_conformal_probe.py;probes/export_week8_results.py;probes/paper_figure_conformal_strata.py |
| probes/dielectric_splitters_auc_summary.json | probes/dielectric_splitters_auc.py;probes/export_week17_results.py;probes/export_week18_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/plot_splitters_auc.py;tests/test_auc_sidecar_and_splitters.py |
| probes/dielectric_target_scale_explore.json | probes/dielectric_target_scale_explore.py;probes/export_week17_results.py |
| probes/dielectric_target_transform_probe_summary.json | probes/dielectric_merge_arm_probe.py;probes/dielectric_target_transform_probe.py;probes/export_week14_results.py;tests/test_dielectric_merge_arm_probe.py;tests/test_dielectric_target_transform_probe.py;tests/test_export_week14_results.py |
| probes/dielectric_unimol_embedding_placebo_summary.json | probes/dielectric_unimol_embedding.py;probes/export_week18_results.py;tests/test_unimol_embedding.py |
| probes/dielectric_unimol_embedding_summary.json | probes/dielectric_unimol_embedding.py;probes/export_week18_results.py;probes/plot_week18.py;tests/test_unimol_embedding.py |
| probes/eta_epsilon_joint_summary.json | probes/build_eta_epsilon_joint_table.py;probes/verify_eta_epsilon_joint_table.py;tests/test_eta_epsilon_joint_table.py |
| probes/four_channel_coverage_summary.json | probes/export_week17_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/four_channel_coverage.py;probes/plot_week17_channels.py;probes/w19_ranking_key.py;probes/w20_ranking_key_v1.py;tests/test_export_week17_results.py;tests/test_four_channel_coverage.py;tests/test_w19_ranking_key.py |
| probes/four_core_registry_prereg.json | probes/build_four_core_registry.py;probes/export_week17_results.py;tests/test_build_four_core_registry.py |
| probes/four_core_registry_summary.json | probes/build_four_core_registry.py;probes/export_week17_results.py |
| probes/g1plus_crawl_round2_evidence.json | probes/export_week7_results.py;tests/test_g1plus_crawl_round2.py |
| probes/g1plus_crawl_round3_evidence.json | probes/export_week8_results.py |
| probes/g1plus_crawl_round4_evidence.json | probes/export_week8_results.py;tests/test_g1plus_crawl_round4.py |
| probes/g1plus_crawl_round5_evidence.json | probes/export_week8_results.py;probes/manual_appendix_reconciliation.py;tests/test_g1plus_crawl_round5.py |
| probes/g1plus_tier0_evidence.json | probes/export_week7_results.py |
| probes/homo_lumo_baselines_summary.json | probes/export_week13_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/homo_lumo_baselines.py;tests/test_l3_backvalidation_prereg.py |
| probes/identity_smiles_drawing_decision_summary.json | probes/export_week16_results.py;probes/identity_smiles_drawing_decision.py;tests/test_export_week16_results.py |
| probes/jstage_corroboration_evidence.json | probes/export_week9_results.py;tests/test_jstage_corroboration.py |
| probes/kpi_funnel_cross_run_summary.json | probes/export_week16_results.py;probes/kpi_funnel_cross_run.py;tests/test_export_week16_results.py |
| probes/kpi_shortlist_extraction_summary.json | probes/kpi_shortlist_extraction.py;tests/test_kpi_shortlist_extraction.py |
| probes/l3_backvalidation_prereg.json | probes/build_liquid_window_features.py;probes/dielectric_channel_v2.py;probes/export_week12_results.py;probes/export_week13_results.py;probes/export_week14_results.py;probes/export_week15_results.py;probes/export_week16_results.py;probes/export_week17_results.py;probes/export_week18_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/export_week21_results.py;probes/export_week22_results.py;probes/export_week23_results.py;probes/export_week24_results.py;probes/homo_lumo_baselines.py;probes/identity_smiles_drawing_decision.py;probes/l3_stage1_pilot.py;probes/verify_reaxys_render_gap_closure.py;tests/test_dielectric_bagging_probe.py;tests/test_dielectric_channel_v2.py;tests/test_export_week14_results.py;tests/test_export_week15_results.py;tests/test_export_week16_results.py;tests/test_export_week17_results.py;tests/test_export_week18_results.py;tests/test_export_week19_results.py;tests/test_l3_backvalidation_prereg.py;tests/test_l3_stage1_pilot.py;tests/test_reaxys_render_gap_closure.py;tests/test_w24_condition_redox.py |
| probes/l3_stage1_pilot_summary.json | probes/dielectric_channel_v2.py;probes/export_week13_results.py;probes/l3_stage1_pilot.py;tests/test_dielectric_bagging_probe.py;tests/test_dielectric_channel_v2.py;tests/test_l3_stage1_pilot.py |
| probes/liquid_window_gate_summary.json | probes/build_liquid_window_features.py;probes/export_week17_results.py;probes/four_channel_coverage.py;probes/reaxys_core_four_crosscheck.py;scripts/verify_liquid_window_gate.py;tests/test_export_week17_results.py;tests/test_liquid_window_gate.py |
| probes/manual_appendix_reconciliation.json | probes/export_week12_results.py;probes/export_week13_results.py;probes/export_week7_results.py;probes/manual_appendix_reconciliation.py;tests/test_manual_appendix_reconciliation.py |
| probes/modern_battery_solvent_reference_lookup_summary.json | scripts/lookup_primary_dielectric_references.py |
| probes/nbs514_alpha_harmonization_summary.json | probes/export_week10_results.py;probes/export_week8_results.py;probes/export_week9_results.py;probes/nbs514_alpha_harmonization_probe.py |
| probes/nbs514_frequency_gate_audit.json | probes/export_week7_results.py;probes/nbs514_frequency_gate_audit.py;tests/test_nbs514_frequency_gate_audit.py |
| probes/paper_figure_conformal_strata_summary.json | probes/export_week10_results.py;probes/export_week9_results.py;probes/paper_figure_conformal_strata.py |
| probes/paper_figure_dataset_growth_summary.json | probes/export_week10_results.py;probes/export_week9_results.py;probes/paper_figure_dataset_growth.py |
| probes/pubchem_identity_layer_summary.json | probes/export_week15_results.py;probes/identity_smiles_drawing_decision.py;probes/pubchem_identity_layer.py;tests/test_export_week15_results.py;tests/test_pubchem_identity_layer.py |
| probes/pubchem_liquid_window_harvest_summary.json | probes/build_liquid_window_features.py;probes/pubchem_liquid_window_harvest.py;scripts/verify_liquid_window_gate.py;tests/test_liquid_window_gate.py;tests/test_pubchem_liquid_window_harvest.py |
| probes/schrodinger_si_reconciliation_summary.json | probes/export_week15_results.py;probes/schrodinger_si_reconciliation.py;tests/test_export_week15_results.py;tests/test_schrodinger_si_reconciliation.py |
| probes/thermoml_local_coverage_summary.json | probes/export_week8_results.py;probes/thermoml_local_coverage_probe.py |
| probes/thermoml_viscosity_coverage_summary.json | probes/build_viscosity_v02.py;probes/export_week15_results.py;probes/thermoml_viscosity_coverage_probe.py;probes/thermoml_viscosity_online_slice.py;tests/test_export_week15_results.py;tests/test_thermoml_viscosity_coverage_probe.py |
| probes/thermoml_viscosity_online_slice_summary.json | probes/export_week16_results.py;probes/thermoml_viscosity_online_slice.py;tests/test_export_week16_results.py |
| probes/viscosity_row_level_summary.json | probes/export_week18_results.py;probes/plot_week18.py;probes/viscosity_row_level_unfreeze.py;probes/w19_chemprop_viscosity.py |
| probes/viscosity_v02_summary.json | probes/build_viscosity_v02.py;probes/export_week17_results.py;tests/test_export_week17_results.py |
| probes/w19_batt_direct_hit_summary.json | probes/export_week19_results.py;probes/w19_batt_direct_hit.py;probes/w19_batt_gap_crosscheck.py;probes/w20_safety_ablation.py;tests/test_w19_batt_direct_hit.py |
| probes/w19_batt_gap_crosscheck_summary.json | probes/export_week19_results.py;probes/w19_batt_gap_crosscheck.py;probes/w21_framework_alignment.py;probes/w21_rank_stability.py;tests/test_w19_batt_gap_crosscheck.py;tests/test_w21_rank_stability.py |
| probes/w19_chemprop_viscosity_summary.json | probes/export_week19_results.py;probes/w19_chemprop_viscosity.py;tests/test_w19_chemprop_viscosity.py |
| probes/w19_safety_channel_registry.json | probes/export_week19_results.py;tests/test_w19_safety_channel.py |
| probes/w19_shots_ledger.json | probes/export_week19_results.py;tests/test_w19_shots_ledger.py |
| probes/w20_epsilon_second_stage_placebo_summary.json | probes/export_week20_results.py;probes/w20_epsilon_second_stage.py;tests/test_w20_epsilon_second_stage.py |
| probes/w20_epsilon_second_stage_summary.json | probes/build_unified_data_document.py;probes/export_week20_results.py;probes/w20_epsilon_second_stage.py;probes/w20_epsilon_second_stage_figure.py;tests/test_w20_epsilon_second_stage.py |
| probes/w20_eta_fairness_summary.json | probes/export_week20_results.py;probes/w20_eta_fairness.py;probes/w20_eta_fairness_figure.py;probes/w20_ranking_key_v1.py;tests/test_w20_eta_fairness.py |
| probes/w20_ranking_key_v1_summary.json | probes/export_week20_results.py;probes/w20_ranking_key_v1.py;tests/test_w20_ranking_key_v1.py |
| probes/w21_eta_thaw_summary.json | probes/export_week21_results.py;probes/w21_eta_thaw.py;tests/test_w21_eta_thaw.py |
| probes/w21_framework_alignment_summary.json | probes/export_week21_results.py;probes/w21_framework_alignment.py;tests/test_w21_framework_alignment.py |
| probes/w21_li_coordination_summary.json | probes/export_week21_results.py;probes/w21_li_coordination.py;probes/w21_li_coordination_figures.py;tests/test_w21_li_coordination.py |
| probes/w21_rank_stability_summary.json | probes/build_unified_data_document.py;probes/export_week21_results.py;probes/w21_figures.py;probes/w21_rank_stability.py;probes/w22_stat_hardening.py;tests/test_w21_rank_stability.py |
| probes/w23_orbital_medium_summary.json | probes/export_week23_results.py;probes/w23_orbital_medium.py;probes/w23_orbital_medium_figures.py;tests/test_w23_orbital_medium.py |
| probes/w23_redox_dscf_summary.json | probes/export_week23_results.py;probes/w23_redox_dscf.py;probes/w23_redox_dscf_figures.py;tests/test_w23_redox_dscf.py |
| probes/w24_2_orca_dft_summary.json | probes/export_week24_results.py;probes/w24_2_orca_dft.py;probes/w24_2_orca_dft_figures.py;tests/test_w24_2_orca_dft.py |
| probes/w24_condition_redox_summary.json | probes/export_week24_results.py;probes/verify_w24_firstpass_reproduction.py;probes/w24_condition_redox.py;probes/w24_condition_redox_figures.py;tests/test_w24_condition_redox.py |
| probes/w26_dielectric_law_summary.json | probes/export_week26_results.py;probes/w26_dielectric_law.py;tests/test_w26_dielectric_law.py |
| probes/w27_dielectric_response_placebo_summary.json | probes/export_week27_results.py;probes/w27_dielectric_response.py;tests/test_w27_dielectric_response.py |
| probes/w27_dielectric_response_summary.json | probes/export_week27_results.py;probes/w27_dielectric_response.py;tests/test_w27_dielectric_response.py |
| probes/w28_dense_hyperparameters_summary.json | probes/export_week28_results.py;probes/w28_dense_hyperparameters.py;tests/test_w28_dense_hyperparameters.py |
| probes/w29_dense_binning_summary.json | probes/export_week29_results.py;probes/w29_dense_binning.py;tests/test_w29_dense_binning.py |
| probes/w30_combination_ladder_summary.json | probes/export_week30_results.py;probes/w30_combination_ladder.py;probes/w31_v6_bridge.py;tests/test_w30_combination_ladder.py |
| probes/w30_ordering_magnitude_summary.json | probes/export_week30_results.py;probes/w30_ordering_magnitude.py;tests/test_w30_ordering_magnitude.py |
| probes/w31_capacity_exchange_summary.json | probes/export_week31_results.py;probes/w31_capacity_exchange.py;tests/test_w31_capacity_exchange.py |
| probes/w32_regularization_ladder_summary.json | probes/export_week32_results.py;probes/w32_presentation_figures.py;probes/w32_regularization_ladder.py;tests/test_w32_presentation_figures.py;tests/test_w32_regularization_ladder.py |
| probes/walden_dn_channel_prereg.json | probes/export_week17_results.py;probes/viscosity_row_level_unfreeze.py;probes/walden_dn_channel.py;scripts/verify_walden_dn_channel.py |
| probes/walden_dn_channel_summary.json | probes/export_week17_results.py;probes/export_week19_results.py;probes/export_week20_results.py;probes/four_channel_coverage.py;probes/walden_dn_channel.py;scripts/verify_walden_dn_channel.py;tests/test_export_week17_results.py;tests/test_walden_dn_channel.py |

## 4. 判据

| 判据 | 内容 | 读数 | 门 | 判决 |
| --- | --- | --- | --- | --- |
| H38e1 | 稳定写入助手可从 probes/export_results_common 导入，volatile 键为时间戳两项 | 2 | 2 | 成立 |
| H38e2 | 仅 volatile 字段不同时，稳定写入不改变盘上字节 | 1 | 1 | 成立 |
| H38e3 | 科学字段变化时仍照写（稳定写入不是「永不写」） | 1 | 1 | 成立 |
| H38e4 | 端到端：连跑两次 W37 导出探针后，被跟踪 summary 相对 HEAD 无改动 | 1 | 1 | 成立 |
| H38e5 | 盘点：带时间戳的被跟踪 JSON 已有写入器迁移到稳定写入（≥ 1） | 1 | 1 | 成立 |
| H38e6 | 0 shot（累计 19）；只跑既有探针与合成临时文件 | 0 | — | 成立 |

## 5. 边界与剩余工作

- 本件只迁移**已观测到会脏树的那一条链路**（W37 导出探针）并把助手放进共享模块；
  其余带时间戳的跟踪件**仍待迁移**（见上表），因此 §11 第 19 条的状态是
  **「机制已修、迁移未完成」**，不是「已关闭」。
- 「无写入器」的那一类是历史产物：它们的写入器已不在仓库里，不会被重跑脏化，
  但也不受守卫保护。
- 稳定写入只对**顶层键**生效（`generated_at_utc` / `elapsed_seconds`）；嵌在子对象里的
  时间戳不在覆盖范围——这是已知盲区。
- 不拟合模型、不触四个冻结读数；不占 shot（累计仍 19）。
