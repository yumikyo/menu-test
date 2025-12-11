import streamlit as st
import os
import asyncio
import json
import nest_asyncio
import time
import shutil
import zipfile
import re
from datetime import datetime
from gtts import gTTS
import google.generativeai as genai
from google.api_core import exceptions
import requests
from bs4 import BeautifulSoup
import edge_tts

# 非同期処理の適用
nest_asyncio.apply()

# ページ設定
st.set_page_config(page_title="Menu Player Generator", layout="wide")

# ==========================================
# 1. サイドバー設定
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
# 2. メイン画面レイアウト
# ==========================================
st.title("🎧 Menu Player Generator")
st.markdown("##### 視覚障害のある方のための「聴くメニュー」生成アプリ")

# --- セッション状態の初期化 ---
if 'captured_images' not in st.session_state:
    st.session_state.captured_images = []
if 'camera_key' not in st.session_state:
    st.session_state.camera_key = 0
if 'generated_result' not in st.session_state:
    st.session_state.generated_result = None
if 'show_camera' not in st.session_state:
    st.session_state.show_camera = False

# ----------------------------------------
# ステップ1：お店情報の入力
# ----------------------------------------
st.markdown("### 1. お店情報の入力")
col1, col2 = st.columns(2)
with col1:
    store_name = st.text_input("🏠 店舗名（必須）", placeholder="例：カフェタナカ")
with col2:
    menu_title = st.text_input("📖 今回のメニュー名（任意）", placeholder="例：冬のランチメニュー")

st.markdown("---")

# ----------------------------------------
# ステップ2：入力方法の選択
# ----------------------------------------
st.markdown("### 2. メニューの登録方法を選ぶ")

input_method = st.radio(
    "どの方法でメニューを登録しますか？",
    ("📂 アルバムから写真を選択", "📷 その場で写真を撮影", "🌐 お店のURLを入力"),
    horizontal=True
)

final_image_list = []
target_url = None

st.write("") 

# --- モードごとの表示 ---
if input_method == "📂 アルバムから写真を選択":
    st.info("スマホやPCに保存されているメニューの写真を選んでください。")
    uploaded_files = st.file_uploader(
        "ここをタップして写真を選択", 
        type=['png', 'jpg', 'jpeg'], 
        accept_multiple_files=True
    )
    if uploaded_files:
        final_image_list.extend(uploaded_files)

elif input_method == "📷 その場で写真を撮影":
    st.info("メニュー表をカメラで撮影します。複数枚の連続撮影も可能です。")
    
    if not st.session_state.show_camera:
        if st.button("📷 カメラを起動する", type="primary"):
            st.session_state.show_camera = True
            st.rerun()
    else:
        if st.button("❌ カメラを閉じる"):
            st.session_state.show_camera = False
            st.rerun()
            
        st.write("▼ シャッターを押した後、下の「追加」ボタンを押してください")
        
        camera_file = st.camera_input("撮影", key=f"camera_{st.session_state.camera_key}")

        if camera_file:
            if st.button("⬇️ この写真を追加して次を撮る", type="primary"):
                st.session_state.captured_images.append(camera_file)
                st.session_state.camera_key += 1
                st.rerun()

    if st.session_state.captured_images:
        final_image_list.extend(st.session_state.captured_images)
        st.success(f"現在 {len(st.session_state.captured_images)} 枚撮影済み")
        
        if st.button("🗑️ 撮影した写真を全てクリア"):
            st.session_state.captured_images = []
            st.rerun()

elif input_method == "🌐 お店のURLを入力":
    st.info("お店のホームページや、食べログ等のメニューページのURLを入力してください。")
    target_url = st.text_input("URLを入力", placeholder="https://...")

# --- プレビュー ---
if final_image_list:
    st.markdown("###### ▼ 登録する画像の確認")
    cols = st.columns(len(final_image_list))
    for idx, img in enumerate(final_image_list):
        if idx < 5: 
            with cols[idx]:
                st.image(img, caption=f"No.{idx+1}", use_container_width=True)

st.markdown("---")

# ==========================================
# 3. 音声生成ロジック
# ==========================================
async def generate_audio_safe(text, filename, voice_code, rate_value):
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice_code, rate=rate_value)
            await comm.save(filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return "EdgeTTS"
        except Exception as e:
            time.sleep(1)
    try:
        tts = gTTS(text=text, lang='ja')
        tts.save(filename)
        return "GoogleTTS"
    except:
        return "Error"

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").replace("　", "_")

def fetch_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style", "header", "footer", "nav"]):
            script.extract()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        return None

# ----------------------------------------
# ステップ3：作成ボタン
# ----------------------------------------
st.markdown("### 3. 音声メニューの作成")

if st.button("🎙️ 音声メニューを作成する", type="primary", use_container_width=True):
    if not api_key or not target_model_name:
        st.error("設定を確認してください（APIキーまたはモデル）")
        st.stop()
    if not store_name:
        st.warning("⚠️ 店舗名を入力してください")
        st.stop()

    has_images = len(final_image_list) > 0
    has_url = bool(target_url)

    if not has_images and not has_url:
        st.warning("⚠️ 画像を選択するか、URLを入力してください")
        st.stop()

    output_dir = os.path.abspath("menu_audio_album")
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    with st.spinner('AIが情報を解析し、台本を作成中...'):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            content_parts = []
            
            # --- プロンプト修正：余計な言葉を排除し、シンプルな出力を強制 ---
            base_prompt = """
            あなたは視覚障害者のためのレストランメニュー読み上げデータ作成のプロです。
            提供された情報を解析し、以下のJSON形式のみを出力してください。
            Markdown記法は不要です。
            
            【重要ルール】
            1. textフィールドには、「まずは」「続いて」などの接続詞や挨拶は一切含めないでください。商品名と価格のみを淡々と読み上げるテキストにしてください。
            2. 価格は「円」まで付けてください。
            3. カテゴリーごとにトラックを分けてください。
            
            出力例:
            [
                {"title": "前菜", "text": "シーザーサラダ、800円。生ハムの盛り合わせ、1200円。"},
                {"title": "飯類", "text": "五目チャーハン、900円。天津飯、1000円。"}
            ]
            """
            
            if has_images:
                content_parts.append(base_prompt + "\n\n以下はメニューの画像です。")
                for f in final_image_list:
                    f.seek(0)
                    content_parts.append({"mime_type": f.type if hasattr(f, 'type') else 'image/jpeg', "data": f.getvalue()})
            elif has_url:
                web_text = fetch_text_from_url(target_url)
                if not web_text:
                    st.error("URL読み取り失敗")
                    st.stop()
                content_parts.append(base_prompt + f"\n\nURLからのテキスト:\n\n{web_text[:30000]}")

            # AI生成
            response = None
            retry_count = 0
            while retry_count < 3:
                try:
                    response = model.generate_content(content_parts)
                    break
                except exceptions.ResourceExhausted:
                    st.warning(f"⚠️ 混雑中... ({retry_count+1}/3)")
                    time.sleep(10)
                    retry_count += 1
                except Exception as e:
                    raise e

            if response is None:
                st.error("❌ 失敗しました。")
                st.stop()

            text_resp = response.text
            start = text_resp.find('[')
            end = text_resp.rfind(']') + 1
            if start == -1 or end == 0:
                 st.error("AIデータの解析に失敗しました。")
                 st.stop()
                 
            menu_data = json.loads(text_resp[start:end])

            # --- イントロ作成（「トラック」という言葉を使わない形式へ） ---
            intro_title = "はじめに・目次"
            intro_text = f"こんにちは、{store_name}です。"
            if menu_title:
                intro_text += f"ただいまより、{menu_title}をご紹介します。"
            intro_text += "今回の内容は以下の通りです。"
            
            # 目次の読み上げ：「2、前菜。3、飯類。」
            for i, track in enumerate(menu_data):
                # イントロが1番なので、メニューは2番から
                track_num = i + 2
                intro_text += f"{track_num}、{track['title']}。"
                
            intro_text += "それでは、ごゆっくりお聴きください。"
            menu_data.insert(0, {"title": intro_title, "text": intro_text})
            
            st.success(f"✅ 台本完成！ 音声ファイルを生成します...")
            progress_bar = st
