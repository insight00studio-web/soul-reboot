"""autonomous/metadata.py - 伏線・パラメータ・L2記憶の更新と完了レポート。

_calculate_viewer_delta: 視聴者フィードバックからパラメータ微調整値を計算
step_update_metadata:    伏線・パラメータ・L2 を一括更新
step_finalize:           Config を進めて完了レポートを出力
"""

from collections import Counter

from sheets_db import SoulRebootDB
from utils import safe_int

from .utils import _safe_encode


def _calculate_viewer_delta(db: SoulRebootDB) -> dict | None:
    """
    直近のアナリティクスとコメント傾向からパラメータ微調整値を計算する。
    各パラメータの調整幅は ±3 以内（Architectの判断が主、視聴者は補助）。
    """
    analytics = db.get_latest_analytics(limit=1)
    if not analytics:
        return None

    latest = analytics[0]
    engagement = float(latest.get("エンゲージメント率", 0)) if latest.get("エンゲージメント率") else 0

    # コメント感情の集計（直近50件）
    recent_sentiments = db.get_recent_sentiments(limit=50)

    if not recent_sentiments:
        # エンゲージメントのみで判断
        if engagement >= 10:
            return {"trust": 0, "awakening": 0, "record": 1, "reason": f"高エンゲージメント{engagement:.1f}%"}
        return None

    counts = Counter(recent_sentiments)
    total = sum(counts.values())

    support_ratio = counts.get("応援", 0) / total  # 応援率
    criticism_ratio = counts.get("批判", 0) / total  # 批判率
    theory_ratio = counts.get("考察", 0) / total  # 考察率

    trust_delta = 0
    awakening_delta = 0
    record_delta = 0
    reasons = []

    # 高エンゲージメント → 記録度 +1〜2
    if engagement >= 10:
        record_delta += 2
        reasons.append(f"エンゲージメント{engagement:.1f}%")
    elif engagement >= 5:
        record_delta += 1

    # 応援多い → 信頼度 +1〜2
    if support_ratio >= 0.5:
        trust_delta += 2
        reasons.append(f"応援{support_ratio*100:.0f}%")
    elif support_ratio >= 0.3:
        trust_delta += 1

    # 批判多い → 覚醒度 +1〜2（緊張感の反映）
    if criticism_ratio >= 0.3:
        awakening_delta += 2
        reasons.append(f"批判{criticism_ratio*100:.0f}%")
    elif criticism_ratio >= 0.15:
        awakening_delta += 1

    # 考察多い → 覚醒度 +1（物語への深い関与）
    if theory_ratio >= 0.3:
        awakening_delta += 1
        reasons.append(f"考察{theory_ratio*100:.0f}%")

    # 上限クリップ（±3）
    trust_delta = max(-3, min(3, trust_delta))
    awakening_delta = max(-3, min(3, awakening_delta))
    record_delta = max(-3, min(3, record_delta))

    if trust_delta == 0 and awakening_delta == 0 and record_delta == 0:
        return None

    return {
        "trust": trust_delta,
        "awakening": awakening_delta,
        "record": record_delta,
        "reason": ", ".join(reasons) if reasons else "視聴者反応",
    }


def step_update_metadata(db: SoulRebootDB, episode_number: int, plot: dict) -> None:
    """
    伏線・パラメータ・L2記憶を更新する。
    """
    print(f"\n[SYNC] STEP 5: 伏線・パラメータ・記憶を更新...")

    # 伏線追加
    for fs in plot.get("foreshadowing_added", []):
        db.add_foreshadowing(
            episode_number=episode_number,
            description=fs.get("description", ""),
            target_episode=fs.get("target_episode", episode_number + 10),
            importance=fs.get("importance", "MID"),
        )

    # 伏線回収
    for res in plot.get("foreshadowing_resolved", []):
        db.resolve_foreshadowing(
            foreshadow_id=res.get("id", ""),
            resolved_episode=episode_number,
            resolution_note=res.get("resolution_note", ""),
        )

    # パラメータ更新（Architectの判断 + 視聴者フィードバック微調整）
    prev = db.get_latest_parameters()
    delta = plot.get("parameter_delta", {})
    new_trust = safe_int(prev.get("信頼度"), 20) + safe_int(delta.get("trust_delta"), 0)
    new_awakening = safe_int(prev.get("覚醒度"), 0) + safe_int(delta.get("awakening_delta"), 0)
    new_record = safe_int(prev.get("記録度"), 5) + safe_int(delta.get("record_delta"), 0)

    # 視聴者フィードバックによる微調整（各パラメータ最大±3）
    viewer_delta = _calculate_viewer_delta(db)
    if viewer_delta:
        new_trust += viewer_delta.get("trust", 0)
        new_awakening += viewer_delta.get("awakening", 0)
        new_record += viewer_delta.get("record", 0)
        trigger_suffix = f" + 視聴者反応({viewer_delta.get('reason', '')})"
    else:
        trigger_suffix = ""

    db.append_parameters(
        episode_number=episode_number,
        trust=new_trust,
        awakening=new_awakening,
        record=new_record,
        trigger_event=delta.get("trigger_event", "") + trigger_suffix,
    )

    # L2記憶更新（上で計算済みの値を再利用し、APIコールを節約）
    l2_entry = {
        "話数": episode_number,
        "タイトル": plot.get("title", ""),
        "要約": plot.get("main_objective", ""),
        "未回収の伏線": ", ".join(
            [fs.get("description", "") for fs in plot.get("foreshadowing_added", [])]
        ),
        "シンジの状態": "(自動更新)",
        "ナギサの状態": "(自動更新)",
        "話の終わりの信頼値": new_trust,
        "話の終わりの覚醒値": new_awakening,
    }
    db.append_memory_l2(l2_entry)
    print("  → 伏線・パラメータ・L2記憶の更新完了")


def step_finalize(db: SoulRebootDB, episode_number: int, plot: dict,
                  advance_episode: bool = True, analytics_summary: dict | None = None) -> None:
    """次の話数をConfigに書き込み、完了レポートを出力する"""
    print(f"\n[FINALIZE] STEP 6: 完了処理...")

    # 次のエピソード番号に更新（--force 再生成時はスキップ）
    if advance_episode:
        db.set_config("CURRENT_EPISODE", episode_number + 1)
    else:
        print(f"  [FORCE再生成] CURRENT_EPISODE は変更しません")

    # 完了レポート
    print("\n" + "=" * 60)
    print(f"DONE: 第{episode_number}話 生成完了！")
    print(f"   タイトル: {_safe_encode(str(plot.get('title', '')))}")
    print(f"   感情曲線: {_safe_encode(str(plot.get('emotional_curve', '')))}")
    print(f"   クリフハンガー: {_safe_encode(plot.get('cliffhanger', ''), 40)}...")
    if analytics_summary and analytics_summary.get("episodes_fetched", 0) > 0:
        print(f"   Analytics: {analytics_summary['episodes_fetched']}話分収集 / 新規コメント{analytics_summary.get('comments_collected', 0)}件")
    print(f"\n[次のアクション] スプレッドシートを確認してください:")
    print(f"   1. [Episodes] タイトル・プロットの確認と修正")
    print(f"   2. [Scripts] 台本の確認（approved=TRUEに変更で承認）")
    print(f"   3. [Comments] 採用コメントの手動調整")
    print(f"   4. [Assets] 画像/音声生成の承認または再生成指示")
    print("=" * 60)
