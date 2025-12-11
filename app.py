import streamlit as st
import os
import sys
import subprocess
import asyncio
import json
import nest_asyncio
from gtts import gTTS # 予備のナレーター

# ==========================================
# 1. 準備：ライブラリの強制ロード
# ==========================================
try:
    import google.generativeai as genai
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-generativeai>=0.8.3"])
    import google.generativeai as genai

import edge_tts

nest_asyncio.apply()
st.set_page_config(page_title="Menu Player", layout="wide")

# ==========================================
# 2. サイドバー設定
# ==========================================
with st.sidebar:
    st.header("🔧 設定")
    api_key = st.text_input("Gemini APIキー", type="password")
    
    # モデル自動取得
    valid_models = []
    if api_key:
        try:
            genai.configure(api_key=api_key)
            all_models = list(genai.list_models())
            valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        except:
            pass
    
    if valid_models:
        st.success(f"使えるAIが見つかりました！ ({len(valid_models)}個)")
        # Flash系を優先的に選択
        default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n), 0)
        target_model_name = st.selectbox("使用するAIモデル", valid_models, index=default_idx)
    else:
        target_model_name = None

    st.divider()
    voice_options = {"女性（七海）": "ja-JP-NanamiNeural", "男性（慶太）": "ja-JP-KeitaNeural"}
    selected_voice = st.selectbox("音声の声 (メイン)", list(voice_options.keys()))
    voice_code = voice_options[selected_voice]

# ==========================================
# 3. メイン画面
# ==========================================
st.title("🎧 Menu Player")
st.markdown("メニュー画像をアップロードすると、AIが音声ガイドを作成します。")

uploaded_files = st.file_uploader(
    "メニュー画像をアップロード", 
    type=['png', 'jpg', 'jpeg'], 
    accept_multiple_files=True
)

if uploaded_files:
    st.image(uploaded_files, width=150, caption=[f"{f.name}" for f in uploaded_files])

# ==========================================
# 4. 音声生成ロジック（二段構え）
# ==========================================
async def generate_audio_safe(text, filename, voice_code):
    try:
        # 1. まずは高音質な Edge TTS に挑戦
        comm = edge_tts.Communicate(text, voice_code)
        await comm.save(filename)
        return "EdgeTTS"
    except Exception as e:
        # 2. ダメなら安定の Google TTS (gTTS) に切り替え
        print(f"EdgeTTS failed: {e}, switching to gTTS...")
        tts = gTTS(text=text, lang='ja')
        tts.save(filename)
        return "GoogleTTS"

if st.button("🎙️ 音声メニューを作成する"):
    if not api_key or not target_model_name:
        st.error("設定を確認してください（APIキーまたはモデル）")
    else:
        with st.spinner('AIがメニューを解析して音声を吹き込んでいます...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(target_model_name)
                
                content_parts = []
                prompt = """
                視覚障害者のためのメニュー読み上げ台本を作成してください。
                提供された画像を解析し、以下のJSON形式のみ出力してください。
                Markdown記法は不要です。
                [{"title": "トラック1：挨拶", "text": "..."}]
                """
                content_parts.append(prompt)
                for f in uploaded_files:
                    content_parts.append({"mime_type": f.type, "data": f.getvalue()})

                response = model.generate_content(content_parts)
                text_resp = response.text
                
                # JSON抽出
                start = text_resp.find('[')
                end = text_resp.rfind(']') + 1
                menu_data = json.loads(text_resp[start:end])
                
                st.success(f"✅ 完成！ ({len(menu_data)}トラック)")

                # トラックごとに音声化
                for i, track in enumerate(menu_data):
                    st.subheader(f"🎵 {track['title']}")
                    st.write(track['text'])
                    
                    fname = f"track_{i+1}.mp3"
                    # ここで安全な音声生成を呼び出す
                    method = asyncio.run(generate_audio_safe(track['text'], fname, voice_code))
                    
                    st.audio(fname)
                    if method == "GoogleTTS":
                        st.caption("※通信状況により予備音声(Google)を使用しました")

            except Exception as e:
                st.error("エラーが発生しました")
                st.write(f"詳細: {e}")
