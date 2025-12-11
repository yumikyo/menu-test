import streamlit as st
import os
import sys
import subprocess
import asyncio
import json
import nest_asyncio
from gtts import gTTS

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
# 2. サイドバー設定（自動ログイン機能付き）
# ==========================================
with st.sidebar:
    st.header("🔧 設定")
    
    # 【変更点】Secrets(金庫)にキーがあれば勝手に使う
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 APIキー認証済み")
    else:
        api_key = st.text_input("Gemini APIキー", type="password")
    
    # モデル自動取得
    valid_models = []
    target_model_name = None
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            all_models = list(genai.list_models())
            valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        except:
            pass
    
    if valid_models:
        # Flash系を優先的に選択
        default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n), 0)
        target_model_name = st.selectbox("使用するAIモデル", valid_models, index=default_idx)
    elif api_key:
        st.error("有効なモデルが見つかりません")

    st.divider()
    voice_options = {"女性（七海）": "ja-JP-NanamiNeural", "男性（慶太）": "ja-JP-KeitaNeural"}
    selected_voice = st.selectbox("音声の声 (メイン)", list(voice_options.keys()))
    voice_code = voice_options[selected_voice]

# ==========================================
# 3. メイン画面
# ==========================================
st.title("🎧 Menu Player")
st.markdown("##### 視覚障害のある方のための「聴くメニュー」生成アプリ")
st.info("メニューの写真をアップロードすると、AIが内容を読み取り、カテゴリーごとに再生できる音声ガイドを作成します。")

uploaded_files = st.file_uploader(
    "📸 メニューの写真を撮る / アップロード", 
    type=['png', 'jpg', 'jpeg'], 
    accept_multiple_files=True
)

if uploaded_files:
    st.image(uploaded_files, width=150, caption=[f"{f.name}" for f in uploaded_files])

# ==========================================
# 4. 音声生成ロジック
# ==========================================
async def generate_audio_safe(text, filename, voice_code):
    try:
        comm = edge_tts.Communicate(text, voice_code)
        await comm.save(filename)
        return "EdgeTTS"
    except Exception as e:
        tts = gTTS(text=text, lang='ja')
        tts.save(filename)
        return "GoogleTTS"

if st.button("🎙️ 音声メニューを作成する"):
    if not api_key or not target_model_name:
        st.error("設定を確認してください（APIキーまたはモデル）")
    else:
        with st.spinner('AIがメニューを読んでいます...そのままお待ちください'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(target_model_name)
                
                content_parts = []
                prompt = """
                あなたは視覚障害者のためのレストランメニュー読み上げのプロです。
                提供された画像を解析し、以下のJSON形式のみを出力してください。
                価格は「円」まで読み上げ、カテゴリー分けをしてください。
                Markdown記法は不要です。
                [{"title": "トラック1：店名・挨拶", "text": "..."}]
                """
                content_parts.append(prompt)
                for f in uploaded_files:
                    content_parts.append({"mime_type": f.type, "data": f.getvalue()})

                response = model.generate_content(content_parts)
                text_resp = response.text
                
                start = text_resp.find('[')
                end = text_resp.rfind(']') + 1
                menu_data = json.loads(text_resp[start:end])
                
                st.success(f"✅ 完成！ {len(menu_data)}個のカテゴリーに分けました。")

                for i, track in enumerate(menu_data):
                    st.subheader(f"🎵 {track['title']}")
                    st.write(track['text'])
                    fname = f"track_{i+1}.mp3"
                    asyncio.run(generate_audio_safe(track['text'], fname, voice_code))
                    st.audio(fname)

            except Exception as e:
                st.error("エラーが発生しました")
                st.write(f"詳細: {e}")
