"""
llm_client.py
Soul Reboot - LLM（Gemini / Claude）共通クライアント

autonomous_engine.py と youtube_analytics.py から共通利用される。
"""

import json
import os
import re
import subprocess
import time

from google import genai
from google.genai import types


# ===================================================================
# JSONパース ユーティリティ
# ===================================================================

def clean_trailing_commas(text: str) -> str:
    """JSON文字列から末尾カンマを除去する"""
    return re.sub(r',\s*([\]}])', r'\1', text)


def parse_json_robust(text: str) -> dict:
    """
    テキストからJSON部分を抽出してパースする。
    1. そのまま json.loads
    2. 末尾カンマ除去して json.loads
    3. ```json ... ``` ブロック抽出して json.loads
    4. 最外の { ... } を抽出して json.loads
    失敗時は JSONDecodeError を raise する。
    """
    # 1. そのままパース
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 末尾カンマ除去
    cleaned = clean_trailing_commas(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. ```json ... ``` ブロック抽出
    json_match = re.search(r'```json\s*([\s\S]*?)```', text)
    if json_match:
        block = json_match.group(1).strip()
        cleaned_block = clean_trailing_commas(block)
        try:
            return json.loads(cleaned_block)
        except json.JSONDecodeError:
            pass

    # 4. 最外の { ... } を抽出
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        extracted = text[start:end + 1]
        cleaned = clean_trailing_commas(extracted)
        return json.loads(cleaned)

    raise json.JSONDecodeError("No valid JSON found", text, 0)


# ===================================================================
# Gemini API クライアント
# ===================================================================

_genai_client: "genai.Client | None" = None


def _get_genai_client(api_key: str = "") -> "genai.Client":
    """module-level シングルトンクライアントを返す（毎呼び出しの生成を回避）"""
    global _genai_client
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if _genai_client is None:
        _genai_client = genai.Client(api_key=api_key)
    return _genai_client


def call_gemini(prompt: str, model_name: str = "gemini-3-flash-preview",
                response_format: str = "json",
                api_key: str = "") -> dict | str:
    """
    Gemini APIを呼び出す（指数バックオフ付きリトライ）。
    response_format="json" の場合、JSONをパースして返す。
    response_format="text" の場合、テキストをそのまま返す。
    """
    client = _get_genai_client(api_key)

    gen_config = types.GenerateContentConfig(temperature=0.8)
    if response_format == "json":
        gen_config = types.GenerateContentConfig(
            temperature=0.8,
            response_mime_type="application/json",
        )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=gen_config,
            )
            break
        except Exception as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt * 5
            print(f"  [RETRY] call_gemini {attempt+1}/3 in {wait}s: {e}")
            time.sleep(wait)

    raw = response.text

    if response_format == "json":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [WARN] JSON parse failed. Raw response: {raw[:500]}")
            cleaned = raw.strip().strip("```json").strip("```").strip()
            cleaned = clean_trailing_commas(cleaned)
            return json.loads(cleaned)
    return raw


# ===================================================================
# Claude Opus CLI クライアント
# ===================================================================

def call_opus(prompt: str, system_prompt: str = "",
              timeout: int = 600, max_retries: int = 3,
              retry_wait: int = 60) -> dict | str:
    """
    Claude Code CLI経由でOpus 4.6を呼び出す。
    JSONブロックが含まれていればパースして返す。なければテキストを返す。
    529 Overloadedエラーは最大max_retries回リトライ（retry_wait秒待機）。
    """
    cmd = ["claude", "-p", "--output-format", "text", "--model", "claude-opus-4-6"]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    # Claude Codeのネスト防止を回避するため、CLAUDECODE環境変数を除去
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    for attempt in range(max_retries + 1):
        print(f"  [OPUS] Claude Opus 4.6 呼び出し中..." + (f" (リトライ {attempt}/{max_retries})" if attempt > 0 else ""))
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            env=env,
        )

        if result.returncode == 0:
            break

        stdout_preview = result.stdout[:300]
        stderr_preview = result.stderr[:300]
        # 529 Overloaded は一時的なサーバー過負荷 → リトライ
        if "529" in stdout_preview or "overloaded_error" in stdout_preview:
            if attempt < max_retries:
                print(f"  [OPUS] 529 Overloaded。{retry_wait}秒後にリトライします...")
                time.sleep(retry_wait)
                continue
        raise RuntimeError(f"Claude CLI error (rc={result.returncode}): stderr={stderr_preview} stdout={stdout_preview}")

    raw = result.stdout.strip()
    print(f"  [OPUS] 応答受信: {len(raw)}文字")

    # JSONブロックの抽出を試みる
    json_match = re.search(r'```json\s*([\s\S]*?)```', raw)
    if json_match:
        raw = json_match.group(1).strip()

    try:
        cleaned = clean_trailing_commas(raw)
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return raw
