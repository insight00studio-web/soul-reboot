import os
import wave
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

def generate_voice_test(voice_name, voice_desc, speaker, text, tone, filename):
    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    model_id = "gemini-2.5-flash-preview-tts"
    
    # 指導プロンプトを追加
    # "Nagisa is a 16-year-old high school girl. She is logical, cool, and a bit expressionless (kuudere). 
    # Please speak in a young, clear, and steady voice of a high school student."
    
    prompt = f"""[Character: {speaker}, {voice_desc}]
[Tone: {tone}]
[Text: {text}]"""

    print(f"Generating {filename} with voice {voice_name}...")
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            )
        )
    )
    
    audio_data = response.candidates[0].content.parts[0].inline_data.data
    
    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(audio_data)
    print(f"Saved {filename}")

if __name__ == "__main__":
    text = "おはよう、シンジ。統計的に有意ではありませんが、概ね良好な一日の始まりです。"
    tone = "静か、論理的"
    
    # 案1: Sulafat に詳細な指示を追加
    generate_voice_test("Sulafat", "16-year-old high school girl, cool, logical, youthful voice", "NAGISA", text, tone, "test_nagisa_sulafat_fix.wav")
    
    # 案2: Kore ("Firm") に詳細な指示を追加
    generate_voice_test("Kore", "16-year-old high school girl, cool, logical, youthful voice", "NAGISA", text, tone, "test_nagisa_kore.wav")
    
    # 案3: Aoede ("Breezy") に詳細な指示を追加
    generate_voice_test("Aoede", "16-year-old high school girl, cool, logical, youthful voice", "NAGISA", text, tone, "test_nagisa_aoede.wav")
