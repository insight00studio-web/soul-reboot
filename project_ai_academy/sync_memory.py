import json
import os

def update_memory(episode_id, summary, l1_details):
    # L2 update (History)
    l2_path = 'c:/Users/uca-n/youtube/project_ai_academy/memory_l2.json'
    with open(l2_path, 'r', encoding='utf-8') as f:
        l2_data = json.load(f)
    
    # Check if episode already exists
    if not any(ep['episode_number'] == episode_id for ep in l2_data['episodes']):
        l2_data['episodes'].append(summary)
        with open(l2_path, 'w', encoding='utf-8') as f:
            json.dump(l2_data, f, ensure_ascii=False, indent=4)

    # L1 update (Recent sliding window)
    l1_path = 'c:/Users/uca-n/youtube/project_ai_academy/memory_l1.json'
    with open(l1_path, 'r', encoding='utf-8') as f:
        l1_data = json.load(f)
    
    l1_data['recent_episodes'].append(l1_details)
    # Maintain only last 3 episodes
    if len(l1_data['recent_episodes']) > 3:
        l1_data['recent_episodes'].pop(0)

    with open(l1_path, 'w', encoding='utf-8') as f:
        json.dump(l1_data, f, ensure_ascii=False, indent=4)

    print(f"Successfully updated Memory for Episode {episode_id}")

# Example logic usage (Can be called by future script generator)
if __name__ == "__main__":
    print("Memory synchronization script initialized.")
