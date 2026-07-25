"""P4 Exit 验收 —— 改单句只重跑该句 TTS/字幕/口型 + 下游（docs/modules/43 §13 第 6 条）。

在 40 句全量变体上，编辑任意一句 → compute_rerun_scope 只波及该句（TTS/SUBTITLE/LIPSYNC）
+ 一次全局 AUDIO_MIX/RENDER；其余 39 句零重跑；TRANSLATION 绝不重跑。
"""

from __future__ import annotations

from p4_samples import SAMPLES

from videoforge_contracts import ReRunStage
from videoforge_domain import ReRunEditKind, compute_rerun_scope

_ALL_IDS = [s.sentence_id for smp in SAMPLES for s in smp.sentences]


def test_editing_one_sentence_scopes_to_only_that_sentence():
    for edited in ("z1-0", "z6-1", "e5-1", "e10-0"):  # 抽查跨样本几句
        scope = compute_rerun_scope([edited], _ALL_IDS)
        # 只该句进逐句重跑
        assert set(scope.per_sentence_stages) == {edited}
        assert scope.per_sentence_stages[edited] == (
            ReRunStage.TTS,
            ReRunStage.SUBTITLE,
            ReRunStage.LIPSYNC,
        )
        # 其余 39 句零重跑
        assert len(scope.unaffected_sentence_ids) == len(_ALL_IDS) - 1
        assert edited not in scope.unaffected_sentence_ids
        # 全局下游一次
        assert scope.global_stages == (ReRunStage.AUDIO_MIX, ReRunStage.RENDER)


def test_translation_never_reruns():
    for edited in _ALL_IDS[:10]:
        scope = compute_rerun_scope([edited], _ALL_IDS)
        stages = [st for v in scope.per_sentence_stages.values() for st in v]
        stages += list(scope.global_stages)
        assert ReRunStage.TRANSLATION not in stages


def test_scope_partition_property_over_full_set():
    # 编辑任意子集：per_sentence 键 == 编辑集；unaffected == 全集 - 编辑集；并集覆盖全集
    for edited in ([], ["z1-0"], ["z3-1", "e2-0", "e9-1"], _ALL_IDS):
        scope = compute_rerun_scope(edited, _ALL_IDS)
        edited_set = set(edited)
        assert set(scope.per_sentence_stages) == edited_set
        assert set(scope.unaffected_sentence_ids) == set(_ALL_IDS) - edited_set
        assert set(scope.unaffected_sentence_ids) | edited_set == set(_ALL_IDS)
        assert bool(scope.global_stages) == bool(edited)


def test_voice_change_same_downstream_scope():
    scope = compute_rerun_scope(
        ["z2-1"],
        _ALL_IDS,
        edit_kind=ReRunEditKind.VOICE_CHANGE,
    )
    assert scope.per_sentence_stages["z2-1"] == (
        ReRunStage.TTS,
        ReRunStage.SUBTITLE,
        ReRunStage.LIPSYNC,
    )
    assert len(scope.unaffected_sentence_ids) == len(_ALL_IDS) - 1
