import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


def update_memory(episode_id: int, summary: dict, l1_details: dict) -> None:
    # L2 update (History)
    l2_path = BASE_DIR / 'memory_l2.json'
    try:
        with open(l2_path, 'r', encoding='utf-8') as f:
            l2_data = json.load(f)
    except FileNotFoundError:
        print(f"[WARN] memory_l2.json が見つかりません: {l2_path}")
        return
    except json.JSONDecodeError as e:
        print(f"[ERROR] memory_l2.json のパースに失敗しました: {e}")
        return

    if not any(ep['episode_number'] == episode_id for ep in l2_data['episodes']):
        l2_data['episodes'].append(summary)
        try:
            with open(l2_path, 'w', encoding='utf-8') as f:
                json.dump(l2_data, f, ensure_ascii=False, indent=4)
        except OSError as e:
            print(f"[ERROR] memory_l2.json の書き込みに失敗しました: {e}")
            return

    # L1 update (Recent sliding window)
    l1_path = BASE_DIR / 'memory_l1.json'
    try:
        with open(l1_path, 'r', encoding='utf-8') as f:
            l1_data = json.load(f)
    except FileNotFoundError:
        print(f"[WARN] memory_l1.json が見つかりません: {l1_path}")
        return
    except json.JSONDecodeError as e:
        print(f"[ERROR] memory_l1.json のパースに失敗しました: {e}")
        return

    l1_data['recent_episodes'].append(l1_details)
    # Maintain only last 3 episodes
    if len(l1_data['recent_episodes']) > 3:
        l1_data['recent_episodes'].pop(0)

    try:
        with open(l1_path, 'w', encoding='utf-8') as f:
            json.dump(l1_data, f, ensure_ascii=False, indent=4)
    except OSError as e:
        print(f"[ERROR] memory_l1.json の書き込みに失敗しました: {e}")
        return

    print(f"Successfully updated Memory for Episode {episode_id}")

# Example logic usage (Can be called by future script generator)
if __name__ == "__main__":
    print("Memory synchronization script initialized.")
