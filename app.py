import streamlit as st
import os
import sys
import subprocess

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
# 2. サイドバー設定
# ==========================================
with st.sidebar:
    st.header("🔧 設定")
    api_key = st.text_input("Gemini APIキー", type="password")
    
    st.divider()
    
    # 【ここが新機能】使えるモデルを自動取得して選べるようにする
    valid_models = []
    if api_key:
        try:
            genai.configure(api_key=api_key)
            # キーを使って、Googleに「使えるモデル一覧」を問い合わせる
            all_models = list(genai.list_models())
            # "generateContent"（文章作成）ができるモデルだけを抽出
            valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
        except Exception as e:
            st.error("キーを確認できませんでした")
    
    if valid_models:
        st.success(f"使えるAIが見つかりました！ ({len(valid_models)}個)")
        # リストから選ぶ方式に変更（デフォルトはFlash系があればそれにする）
        default_index = 0
        for i, name in enumerate(valid_models):
            if "flash" in name:
                default_index = i
                break
        target_model_name = st.selectbox("使用するAIモデル", valid_models, index=default_index)
    else:
        if api_key:
            st.error("⚠️ このキーで使えるAIモデルが見つかりません。")
            st.caption("原因: プロジェクトでGenerative Language APIが有効になっていない可能性があります。")
            target_model_name = None
        else:
            target_model_name = None

    st.divider()
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
# 4. 実行処理
# ==========================================
if st.button("🎙️ 音声メニューを作成する"):
    if not api_key:
        st.warning("⚠️ サイドバーにAPIキーを入力してください")
    elif not target_model_name:
        st.error("⚠️ 使えるAIモデルが見つからないため実行できません。サイドバーを確認してください。")
    else:
        with st.spinner(f'AI ({target_model_name}) がメニューを解析中...'):
            try:
                genai.configure(api_key=api_key)
                
                # 選ばれたモデルを使う
                model = genai.GenerativeModel(target_model_name)
                
                content_parts = []
                prompt_text = """
                あなたは視覚障害者のためにレストランメニュー読み上げのプロです。
                提供された画像を解析し、以下のJSON形式のみを出力してください。
                Markdown記法(```json)は含めないでください。
                [{"title": "トラック1：はじめに", "text": "店名と挨拶..."}]
                """
                content_parts.append(prompt_text)

                for file in uploaded_files:
                    image_data = {"mime_type": file.type, "data": file.getvalue()}
                    content_parts.append(image_data)

                response = model.generate_content(content_parts)
                
                text = response.text
                start = text.find('[')
                end = text.rfind(']') + 1
                if start == -1:
                    raise ValueError("AIからの応答を解析できませんでした。")
                
                menu_data = json.loads(text[start:end])
                
                st.success(f"✅ 成功！ {len(menu_data)}個のトラックを生成しました。")

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
