import streamlit as st
import os
import sys
import subprocess
import time

# ==========================================
# 1. 準備：ライブラリの強制ロード
# ==========================================
try:
    import google.generativeai as genai
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-generativeai>=0.8.3"])
    import google.generativeai as genai

import edge_tts
import asyncio
import json
import nest_asyncio

nest_asyncio.apply()
st.set_page_config(page_title="Menu Player", layout="wide")

# ==========================================
# 2. 設定サイドバー
# ==========================================
with st.sidebar:
    st.header("🔧 設定")
    api_key = st.text_input("Gemini APIキー", type="password")
    
    # バージョン表示（確認用）
    st.caption(f"AI Library Version: {genai.__version__}")
    
    voice_options = {"女性（七海）": "ja-JP-NanamiNeural", "男性（慶太）": "ja-JP-KeitaNeural"}
    selected_voice = st.selectbox("音声の声", list(voice_options.keys()))
    voice_code = voice_options[selected_voice]

# ==========================================
# 3. メイン画面
# ==========================================
st.title("🎧 Menu Player")
st.markdown("メニュー画像をアップロードすると、AIが音声ガイドを作成します。")

uploaded_files = st.file_uploader(
    "メニュー画像をアップロード（複数枚OK）", 
    type=['png', 'jpg', 'jpeg'], 
    accept_multiple_files=True
)

if uploaded_files:
    st.image(uploaded_files, width=150, caption=[f"{f.name}" for f in uploaded_files])

# ==========================================
# 4. 実行処理（ここをシンプルかつ強力にしました）
# ==========================================
if st.button("🎙️ 音声メニューを作成する"):
    if not api_key:
        st.warning("⚠️ サイドバーにAPIキーを入力してください")
    else:
        with st.spinner('AIがメニューを解析中...'):
            try:
                # API設定
                genai.configure(api_key=api_key)
                
                # 画像の準備
                content_parts = []
                prompt_text = """
                あなたは視覚障害者のためのレストランメニュー読み上げのプロです。
                提供された画像を解析し、以下のJSON形式のみを出力してください。
                Markdown記法(```json)は含めないでください。
                [{"title": "トラック1：はじめに", "text": "店名と挨拶..."}]
                """
                content_parts.append(prompt_text)

                for file in uploaded_files:
                    image_data = {"mime_type": file.type, "data": file.getvalue()}
                    content_parts.append(image_data)

                # 【重要】モデル自動切り替えロジック
                # まずは最新のFlashを試す
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    response = model.generate_content(content_parts)
                except Exception:
                    # Flashがダメなら、安定版のProを試す（バックアップ）
                    st.warning("⚠️ Flashモデルが混雑しているため、Proモデルに切り替えて再試行します...")
                    model = genai.GenerativeModel('gemini-pro')
                    response = model.generate_content(content_parts)

                # 結果の処理
                text = response.text
                # JSON部分を無理やり抽出する（AIが余計な文字を入れても大丈夫なように）
                start = text.find('[')
                end = text.rfind(']') + 1
                if start == -1:
                    raise ValueError("AIがメニューを認識できませんでした。")
                
                menu_data = json.loads(text[start:end])
                
                st.success(f"✅ 成功しました！ {len(menu_data)}個のトラックを生成します。")

                # 音声生成
                async def gen_audio(t, f):
                    comm = edge_tts.Communicate(t, voice_code)
                    await comm.save(f)

                for i, track in enumerate(menu_data):
                    st.subheader(f"🎵 {track['title']}")
                    st.write(track['text'])
                    fname = f"track_{i+1}.mp3"
                    asyncio.run(gen_audio(track['text'], fname))
                    st.audio(fname)

            except Exception as e:
                st.error("エラーが発生しました。")
                st.write(f"詳細: {e}")
                st.info("ヒント: 画像を変えてみるか、APIキーを再確認してください。")
