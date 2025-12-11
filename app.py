import streamlit as st
import os
import sys
import subprocess
import asyncio
import json
import nest_asyncio
import time
import shutil
import zipfile
import re
from datetime import datetime
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
# 2. サイドバー設定
# ==========================================
with st.sidebar:
    st.header("🔧 設定")
    
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 APIキー認証済み")
    else:
        api_key = st.text_input("Gemini APIキー", type="password")
    
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
        default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n), 0)
        target_model_name = st.selectbox("使用するAIモデル", valid_models, index=default_idx)
    elif api_key:
        st.error("有効なモデルが見つかりません")

    st.divider()
    
    st.subheader("🗣️ 音声設定")
    voice_options = {"女性（七海）": "ja-JP-NanamiNeural", "男性（慶太）": "ja-JP-KeitaNeural"}
    selected_voice = st.selectbox("声の種類", list(voice_options.keys()))
    voice_code = voice_options[selected_voice]
    
    speed_options = {
        "標準 (±0%)": "+0%", 
        "少し速く (1.2倍)": "+20%", 
        "サクサク (1.4倍/推奨)": "+40%", 
        "爆速 (2.0倍)": "+100%"
    }
    selected_speed_label = st.selectbox("読み上げ速度", list(speed_options.keys()), index=2)
    rate_value = speed_options[selected_speed_label]

# ==========================================
# 3. メイン画面
# ==========================================
st.title("🎧 Menu Player")
st.markdown("##### 視覚障害のある方のための「聴くメニュー」生成アプリ")

# --- 追加機能：店舗情報の入力フォーム ---
col1, col2 = st.columns(2)
with col1:
    store_name = st.text_input("🏠 店舗名（必須）", placeholder="例：カフェタナカ")
with col2:
    menu_title = st.text_input("📖 今回のメニュー名（任意）", placeholder="例：冬のランチメニュー")

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
async def generate_audio_safe(text, filename, voice_code, rate_value):
    # 3回リトライ
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice_code, rate=rate_value)
            await comm.save(filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return "EdgeTTS"
        except Exception as e:
            time.sleep(1)
            
    # 予備音声
    try:
        tts = gTTS(text=text, lang='ja')
        tts.save(filename)
        return "GoogleTTS"
    except:
        return "Error"

# ファイル名に使えない文字を安全な文字に変換する関数
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").replace("　", "_")

# --- 生成ボタンの条件に「店舗名」を追加 ---
if st.button("🎙️ 音声メニューを作成する"):
    if not api_key or not target_model_name:
        st.error("設定を確認してください（APIキーまたはモデル）")
    elif not store_name:
        st.warning("⚠️ 店舗名を入力してください（ファイル名に使用します）")
    elif not uploaded_files:
        st.warning("⚠️ 画像をアップロードしてください")
    else:
        # フォルダのリセット
        output_dir = os.path.abspath("menu_audio_album")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

        with st.spinner('AIが画像を解析し、台本を作成中...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(target_model_name)
                
                content_parts = []
                prompt = """
                あなたは視覚障害者のためのレストランメニュー読み上げのプロです。
                提供された画像を解析し、以下のJSON形式のみを出力してください。
                価格は「円」まで読み上げ、カテゴリー分けをしてください。
                Markdown記法は不要です。
                
                出力例:
                [
                    {"title": "前菜", "text": "まずは前菜のメニューです。..."},
                    {"title": "メイン料理", "text": "続いてメイン料理のご紹介です。..."}
                ]
                """
                content_parts.append(prompt)
                for f in uploaded_files:
                    content_parts.append({"mime_type": f.type, "data": f.getvalue()})

                response = model.generate_content(content_parts)
                text_resp = response.text
                
                start = text_resp.find('[')
                end = text_resp.rfind(']') + 1
                menu_data = json.loads(text_resp[start:end])

                # --- 追加機能：イントロダクション（目次）の自動生成 ---
                intro_title = "はじめに・目次"
                intro_text = f"こんにちは、{store_name}です。"
                if menu_title:
                    intro_text += f"ただいまより、{menu_title}をご紹介します。"
                
                intro_text += "今回の内容は以下の通りです。"
                
                # 目次の作成（Track 2以降の内容を予告）
                for i, track in enumerate(menu_data):
                    # 実際のトラック番号は「イントロ(1)」が入るため +2 になる
                    intro_text += f"トラック{i+2}は、{track['title']}。"
                
                intro_text += "それでは、ごゆっくりお聴きください。"
                
                # リストの先頭（インデックス0）にイントロを追加
                menu_data.insert(0, {"title": intro_title, "text": intro_text})
                
                st.success(f"✅ 台本完成！ 全{len(menu_data)}トラック（イントロ含む）を生成します。")
                
                progress_bar = st.progress(0)
                
                # 音声生成ループ
                for i, track in enumerate(menu_data):
                    track_number = f"{i+1:02}" # 01, 02...
                    safe_title = sanitize_filename(track['title'])
                    filename = f"{track_number}_{safe_title}.mp3"
                    save_path = os.path.join(output_dir, filename)
                    
                    st.subheader(f"🎵 Track {track_number}: {track['title']}")
                    st.write(track['text'])
                    
                    method = asyncio.run(generate_audio_safe(track['text'], save_path, voice_code, rate_value))
                    
                    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                        st.audio(save_path)
                    else:
                        st.error("音声ファイルの生成に失敗しました")
                    
                    progress_bar.progress((i + 1) / len(menu_data))
                    time.sleep(0.5)

                # ==========================================
                # ZIPファイルの作成（名前カスタマイズ版）
                # ==========================================
                # 現在の日時を取得
                date_str = datetime.now().strftime('%Y%m%d')
                safe_store_name = sanitize_filename(store_name)
                
                # ファイル名: 店舗名_日付.zip
                zip_filename = f"{safe_store_name}_{date_str}.zip"
                
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(output_dir):
                        for file in files:
                            zipf.write(os.path.join(root, file), file)
                
                zip_size_mb = os.path.getsize(zip_filename) / (1024 * 1024)
                
                if zip_size_mb < 0.01:
                    st.error(f"⚠️ エラー: ZIP作成失敗（サイズ小）")
                else:
                    st.success(f"📦 ZIP作成完了: {zip_filename}")
                    
                    with open(zip_filename, "rb") as fp:
                        st.download_button(
                            label=f"📥 {zip_filename} をダウンロード",
                            data=fp,
                            file_name=zip_filename,
                            mime="application/zip"
                        )

            except Exception as e:
                st.error("エラーが発生しました")
                st.write(f"詳細: {e}")
