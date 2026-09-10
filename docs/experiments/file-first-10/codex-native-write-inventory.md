# Codex 两份 root rollout：全量 native 修改文件清单

此表独立扫描原始 `patch_apply_end`，再附附近的 `tools.apply_patch` 调用与其同 ID 外层结果作候选关联；不是从旧题、fixer 总结或新模型答案反推。实际 write 由事件自己的 `success/changes` 证明。外层 call_* 与事件 exec-* 不同，不能以邻行或空 `{}` 结果证明嵌套绑定。完整时间、两套 call_id、独立事件哈希和子线程元数据见 [codex-native-write-inventory.json](codex-native-write-inventory.json)。

范围：118 次 apply_patch 调用，6 次有明确失败结果；独立扫描 113 个成功 patch 事件。按时间/路径候选关联，112 次调用附近覆盖这些事件，其中一调用附近有两个事件；该统计不是调用归属已证实的声明。144 个 `(source_basename, 文件路径)` 组合中，77 个有 execute 完成之后的事件。两个 rollout 仅直接证明 2 个后置产品源码/配置文件；其余是生成内产品修改、工具链或报告。`A/M/D` 信息以独立事件 stdout 为准。

时段依据：`rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl:7687`，`2026-08-16T23:49:46.899Z`。

| 完整 source basename | 修改路径（相对历史 AIPPT_830_test；外部路径保留） | 时段 | call / event / result 候选关联物理行（非 ID 绑定） |
|---|---|---|---|
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `AGENTS.md` | execute 内/之前 | 770 → 771 → 772 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/entryability/EntryAbility.ets` | execute 内/之前 | 4356 → 4357 → 4358 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/pages/BaseWXPayEntryPage.ets` | execute 内/之前 | 4386 → 4387 → 4388 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/pages/GuideDifficulty1Component.ets` | execute 内/之前 | 3037 → 3038 → 3039 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/pages/Index.ets` | execute 内/之前 | 4356 → 4357 → 4358 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/pages/LaunchAgreementDialog.ets` | execute 后 | 8066 → 8067 → 8068 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/pages/MainPage.ets` | execute 内/之前 | 4356 → 4357 → 4358 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/ets/pages/WXCallbackPage.ets` | execute 内/之前 | 4386 → 4387 → 4388 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `entry/src/main/resources/base/profile/main_pages.json` | execute 内/之前 | 4356 → 4357 → 4358 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/.a2h/impl-claims.json` | execute 内/之前 | 5858 → 5859 → 5860; 6281 → 6282 → 6283; 6668 → 6669 → 6670; 6983 → 6984 → 6985; 7571 → 7572 → 7573 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/.a2h/plan-coverage.json` | execute 内/之前 | 1437 → 1438 → 1439 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/api-inventory/api-inventory.json` | execute 内/之前 | 1308 → 1309 → 1310 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/api-inventory/api-inventory.md` | execute 内/之前 | 541 → 542 → 543; 1322 → 1323 → 1324 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/api-inventory/data-chains/chain-auth.md` | execute 内/之前 | 1322 → 1323 → 1324 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/cross-module-contracts.md` | execute 内/之前 | 333 → 334 → 335 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/feature-base.md` | execute 内/之前 | 621 → 622 → 623; 1030 → 1031 → 1032 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/feature-cross-validation-report.md` | execute 内/之前 | 1083 → 1084 → 1085 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/feature-index.md` | execute 内/之前 | 621 → 622 → 623; 5868 → 5869 → 5870; 6295 → 6296 → 6297; 6701 → 6702 → 6703; 6993 → 6994 → 6995; 7566 → 7567 → 7568 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/feature-plan.md` | execute 内/之前 | 1408 → 1409 → 1410; 1536 → 1537 → 1538 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F001-startup-privacy-guide.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F002-input-document-import.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F003-outline-generation-editing.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F004-template-browse-filter-search.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F005-ppt-generation-preview-share.md` | execute 内/之前 | 904 → 905 → 906; 1035 → 1036 → 1037 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F006-works-and-collections.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F007-auth-and-account.md` | execute 内/之前 | 904 → 905 → 906; 1035 → 1036 → 1037; 1060 → 1061 → 1062 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F008-membership-and-payment.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F009-web-video-system-routing.md` | execute 内/之前 | 904 → 905 → 906 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/features/F010-push-analytics-ads-safety.md` | execute 内/之前 | 904 → 905 → 906; 1035 → 1036 → 1037 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/plans/coverage-matrix.md` | execute 内/之前 | 1421 → 1422 → 1423 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/plans/feature-plan.md` | execute 内/之前 | 1536 → 1537 → 1538 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/source-coverage-report.md` | execute 内/之前 | 1078 → 1079 → 1080 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui-manifest.md` | execute 内/之前 | 460 → 461 → 462; 689 → 690 → 691; 3143 → 3144 → 3145; 3914 → 3915 → 3916; 4299 → 4300 → 4301; 5868 → 5869 → 5870; 6295 → 6296 → 6297; 6701 → 6702 → 6703; 6993 → 6994 → 6995; 7566 → 7567 → 7568 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0008_CreateOutLinePage.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0010_FileListPage.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0012_GuideActivity.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0016_ManageRenewActivity.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0017_MemberCenterActivitiy.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0020_PPTTemplatePreviewPage.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0022_PushDetailActivity.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0026_SplashActivity.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0031_MineFragment.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0039_HomeFragment.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0041_RecommendFragment.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/baseline/ui/page_0043_WorksFragment.md` | execute 内/之前 | 522 → 523 → 524 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/decision-ledger.md` | execute 内/之前 | 705 → 706 → 707; 783 → 784 → 785; 811 → 812 → 813; 853 → 854 → 855; 1044 → 1045 → 1046; 1097 → 1098 → 1099; 1184 → 1185 → 1186; 1298 → 1299 → 1300; 1303 → 1304 → 1305; 1446 → 1447 → 1448 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/base-contracts.md` | execute 内/之前 | 5506 → 5507 → 5508 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_01_brief.md` | execute 内/之前 | 4776 → 4777 → 4778 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_02_brief.md` | execute 内/之前 | 4902 → 4903 → 4904 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_03_brief.md` | execute 内/之前 | 5106 → 5107 → 5108 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_04_brief.md` | execute 内/之前 | 5177 → 5178 → 5179 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_05_brief.md` | execute 内/之前 | 5293 → 5294 → 5295 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_06_brief.md` | execute 内/之前 | 5432 → 5433 → 5434 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/base_07_brief.md` | execute 内/之前 | 5551 → 5552 → 5553 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/batch_01_brief.md` | execute 内/之前 | 3143 → 3144 → 3145 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/batch_02_brief.md` | execute 内/之前 | 3914 → 3915 → 3916 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/batch_03_brief.md` | execute 内/之前 | 4299 → 4300 → 4301 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/final_structural_closure_brief.md` | execute 内/之前 | 7561 → 7562 → 7563 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/group_1_brief.md` | execute 内/之前 | 5863 → 5864 → 5865 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/group_2_brief.md` | execute 内/之前 | 6267 → 6268 → 6269 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/group_3_brief.md` | execute 内/之前 | 6663 → 6664 → 6665 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/group_4_brief.md` | execute 内/之前 | 6978 → 6979 → 6980 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/execution/briefs/group_5_brief.md` | execute 内/之前 | 7209 → 7210 → 7211 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/feature-coverage-report.md` | execute 内/之前 | 1097 → 1098 → 1099 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/migration-report.md` | execute 内/之前 | 2006 → 2007 → 2008; 3152 → 3153 → 3154; 3914 → 3915 → 3916; 4299 → 4300 → 4301; 5506 → 5507 → 5508; 6060 → 6061 → 6062; 6322 → 6323 → 6324; 6727 → 6728 → 6729; 7033 → 7034 → 7035; 7676 → 7677 → 7678 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/placeholder-registry.md` | execute 内/之前 | 5868 → 5869 → 5870; 6290 → 6291 → 6292; 6681 → 6682 → 6683; 6696 → 6697 → 6698; 6988 → 6989 → 6990; 7218 → 7219 → 7220; 7566 → 7567 → 7568; 7671 → 7672 → 7673 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/ui-coverage-report.md` | execute 内/之前 | 689 → 690 → 691 |
| `rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl` | `spec/ui-coverage-tasks.md` | execute 内/之前 | 689 → 690 → 691 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/a2h-functional-merge/scripts/merge_functional_into_facttree.py` | execute 后 | 637 → 640 → 638; 663 → 664 → 665; 678 → 681 → 679 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/assert_round_complete.py` | execute 后 | 6214 → 6215 → 6216 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/build_judge_input.py` | execute 后 | 4038 → 4039 → 4040 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/materialize_blackbox_to_factree.py` | execute 后 | 3185 → 3186 → 3187 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/replay_place_artifacts.py` | execute 后 | 3927 → 3928 → 3929; 3948 → 3949 → 3950 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/run_phase2_android_survey.py` | execute 后 | 1856 → 1857 → 1858 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/trip_assign.py` | execute 后 | 3185 → 3186 → 3187 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/arkts-visual-verify/scripts/validate_batch_output.py` | execute 后 | 5629 → 5630 → 5631; 5664 → 5665 → 5666 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/toolkit-fact-indexer/scripts/harmony-migration-toolkit/bundled_spec_tools/extractors/navigation_extractor.py` | execute 后 | 304 → 307 → 305 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/toolkit-fact-indexer/scripts/harmony-migration-toolkit/stages/_util.py` | execute 后 | 247 → 248 → 249 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/toolkit-fact-indexer/scripts/harmony-migration-toolkit/stages/export_agent_bundle.py` | execute 后 | 304 → 307 → 305 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `.agents/skills/toolkit-fact-indexer/scripts/toolkit_to_fact_tree_draft.py` | execute 后 | 1856 → 1857 → 1858 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `build_out.log` | execute 后 | 7878 → 7879 → 7880 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `build-profile.json5` | execute 后 | 4943 → 4944 → 4945 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `docs/autofix-log/round-0/visual-fixer-summary.md` | execute 后 | 6167 → 6168 → 6169 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `docs/autofix-log/round-1/visual-fixer-summary.md` | execute 后 | 6971 → 6972 → 6973 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `docs/autofix-log/round-2/visual-fixer-summary.md` | execute 后 | 7686 → 7687 → 7688 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/_state.yaml` | execute 后 | 5919 → 5920 → 5921; 6787 → 6788 → 6789; 7581 → 7582 → 7583; 7789 → 7790 → 7791 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/baseline-blocked/BLOCKED_baseline_MineFragment_trip_1_logged_out.md` | execute 后 | 1781 → 1782 → 1783 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/baseline-blocked/BLOCKED_baseline_RecommendFragment_trip_1_logged_out.md` | execute 后 | 1781 → 1782 → 1783 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/baseline-blocked/BLOCKED_baseline_SplashActivity_trip_1_logged_out.md` | execute 后 | 1781 → 1782 → 1783 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/baseline-blocked/BLOCKED_baseline_WorksFragment_trip_1_logged_out.md` | execute 后 | 1781 → 1782 → 1783 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/_index.md` | execute 后 | 5919 → 5920 → 5921 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/_summary.md` | execute 后 | 5919 → 5920 → 5921 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/_systemic/SYSTEMIC_guide-progress-state-drift.md` | execute 后 | 5864 → 5865 → 5866 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/_systemic/SYSTEMIC_nav-back-layout-drift.md` | execute 后 | 5864 → 5865 → 5866 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PAboutUsActivity_missing_element_back-button.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PCreateOutLinePage_layout_bug_back-title-overlap.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PFileListPage_missing_element_back-button.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDetailsFragment_component_mismatch_progress-state.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDetailsFragment_layout_bug_back-position.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDifficulty1Fragment_layout_drift_progress-indicator.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDifficulty1Fragment_layout_drift_top-navigation.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDifficulty2Fragment_layout_drift_progress-indicator.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDifficulty2Fragment_layout_drift_top-navigation.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDifficulty3Fragment_layout_drift_progress-indicator.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/ALIGN_PGuideDifficulty3Fragment_layout_drift_top-navigation.md` | execute 后 | 5869 → 5870 → 5871 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PAccountInfoActivity.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PChoicePPTTemplatePage.md` | execute 后 | 6223 → 6224 → 6225; 6232 → 6233 → 6234 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PCustomerServiceWebActivity.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PFileConfirmDialog.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PFillPPTQueryDialog.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PPPTCreatingDialog.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PPPTFilePage.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PPPTTemplatePreviewPage.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PRecommendListFragment.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-0/ui/BLOCKED_PSearchPagePage.md` | execute 后 | 6223 → 6224 → 6225 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/_delta.md` | execute 后 | 6787 → 6788 → 6789 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/_index.md` | execute 后 | 6787 → 6788 → 6789 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/_summary.md` | execute 后 | 6787 → 6788 → 6789 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/ui/_systemic/SYSTEMIC_guide-progress-state-drift.md` | execute 后 | 6770 → 6771 → 6772 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/ui/ALIGN_PGuideDetailsFragment_component_mismatch_progress-state.md` | execute 后 | 6770 → 6771 → 6772 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/ui/ALIGN_PGuideDifficulty1Fragment_layout_drift_progress-indicator.md` | execute 后 | 6770 → 6771 → 6772 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/ui/ALIGN_PGuideDifficulty2Fragment_layout_drift_progress-indicator.md` | execute 后 | 6770 → 6771 → 6772 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/ui/ALIGN_PGuideDifficulty3Fragment_layout_drift_progress-indicator.md` | execute 后 | 6770 → 6771 → 6772 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-1/ui/BLOCKED_PChoicePPTTemplatePage.md` | execute 后 | 6800 → 6801 → 6802 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-2/_delta.md` | execute 后 | 7581 → 7582 → 7583 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-2/_index.md` | execute 后 | 7581 → 7582 → 7583 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/round-2/_summary.md` | execute 后 | 7581 → 7582 → 7583 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/fix/stubborn/ALIGN_PFileListPage_missing_element_back-button/ALIGN_PFileListPage_missing_element_back-button.md` | execute 后 | 7789 → 7790 → 7791 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/toolkit-fact-tree.json` | execute 后 | 797 → 798 → 799; 1856 → 1857 → 1858; 3185 → 3186 → 3187 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/_trip_retry_queue.json` | execute 后 | 1428 → 1429 → 1430 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/android_dump_round2/trip_2_logged_in_vip/FileListPage.blackbox.android.xml` | execute 后 | 3600 → 3601 → 3602 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/batches/trip_1_logged_out_batch_01/manifest.json` | execute 后 | 5886 → 5887 → 5888 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/batches/trip_1_logged_out_batch_02/manifest.json` | execute 后 | 5886 → 5887 → 5888 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/batches/trip_2_logged_in_vip_batch_01/manifest.json` | execute 后 | 5886 → 5887 → 5888 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/edgewalk/chunk0_extras.md` | execute 后 | 946 → 947 → 949 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/edgewalk/chunk0_safety_review.md` | execute 后 | 946 → 947 → 949 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/edgewalk/chunk0_steps.json` | execute 后 | 946 → 948 → 949 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/edgewalk/project_rules.md` | execute 后 | 946 → 947 → 949 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/edgewalk/run_env.md` | execute 后 | 946 → 947 → 949 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/phase2_batches/phase2_trip_1_logged_out_chunk_01/manifest.json` | execute 后 | 1419 → 1420 → 1421; 1428 → 1429 → 1430 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/phase2_batches/phase2_trip_1_logged_out_chunk_03/manifest.json` | execute 后 | 1619 → 1620 → 1621 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/progress.json` | execute 后 | 894 → 895 → 896 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/replay_annotations.json` | execute 后 | 3582 → 3583 → 3584 |
| `rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl` | `spec/visual-verify/trip_gate_overrides.json` | execute 后 | 1724 → 1725 → 1726 |

所有原始成功 native 事件均被独立收录。08-21 的 L304、637、678 外层先 yield，附近相应路径的事件在 L307、640、681；这三项为工具链文件，不能因首次返回 `Script running` 误列失败。候选关联仅供回到原文检查，不作为 write 事实的依赖条件。

这里的完整性仅针对两份 root rollout 可见的 native 写入；子代理内补丁、构建脚本间接生成物、IDE/人工外部修改均不由该表补造。非 native 的报告加工/截图搬运见 candidate-codex.md 的补充账。
