import os
from dotenv import load_dotenv
from asset_generator import AssetGenerator

load_dotenv()

def test_nagisa():
    sid = os.environ.get("SOUL_REBOOT_SPREADSHEET_ID")
    generator = AssetGenerator(sid)
    
    # Nagisa's first line
    text = "おはよう、シンジ。統計的に有意ではありませんが、概ね良好な一日の始まりです。"
    tone = "冷静、論理的"
    ep_num = 1
    row_idx = 6 # スプレッドシートの行番号（ナギサの初台本行）

    print(f"Testing new settings for NAGISA (Kore + Profile prompt)")
    path = generator.generate_voice("NAGISA", text, tone, ep_num, row_idx)
    
    if path:
        print(f"Success! Saved to: {path}")
    else:
        print("Failed to generate (Likely rate limit).")

if __name__ == "__main__":
    test_nagisa()
