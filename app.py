import streamlit as st
import os
import asyncio
import json
import nest_asyncio
import time
import shutil
import zipfile
import re
import base64
from datetime import datetime
from gtts import gTTS
import google.generativeai as genai
from google.api_core import exceptions
import requests
from bs4 import BeautifulSoup
import edge_tts

nest_asyncio.apply()
st.set_page_config(page_title="Menu Player Generator", layout="wide")

# ==========================================
# 1. HTMLプレイヤー作成関数（ここが新機能！）
# ==========================================
def create_standalone_html_player(store_name, menu_data):
    """
    音声データ(Base64)とプレイヤープログラム(JS)を埋め込んだ
    単独で動くHTMLファイルを生成する
    """
    # プレイリスト用データの作成
    playlist_js = []
    
    # menu_dataには {title, text, path} が入っている想定
    # pathにあるファイルを読み込んでBase64にする
    for track in menu_data:
        file_path = track['path']
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()
                playlist_js.append({
                    "title": track['title'],
                    "src": f"data:audio/mp3;base64,{b64_data}"
                })

    # PythonリストをJSON文字列に変換
    playlist_json_str = json.dumps(playlist_js, ensure_ascii=False)

    # HTMLテンプレート
    html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{store_name} - 音声メニュー</title>
    <style>
        body {{ font-family: sans-serif; background-color: #f0f2f6; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
        h1 {{ text-align: center; color: #333; font-size: 1.5em; margin-bottom: 20px; }}
        .current-box {{ background: #fff5f5; border: 2px solid #ff4b4b; border-radius: 10px; padding: 15px; text-align: center; margin-bottom: 20px; }}
        .current-title {{ font-size: 1.4em; font-weight: bold; color: #ff4b4b; }}
        .controls {{ display: flex; gap: 10px; margin-bottom: 20px; }}
        button {{ flex: 1; padding: 15px 5px; font-size: 1.1em; font-weight: bold; color: white; background-color: #ff4b4b; border: none; border-radius: 8px; cursor: pointer; }}
        button:disabled {{ background-color: #ccc; }}
        .list-area {{ border-top: 1px solid #eee; padding-top: 10px; }}
        .track-item {{ padding: 12px; border-bottom: 1px solid #eee; cursor: pointer; }}
        .track-item.active {{ background: #ffecec; color: #ff4b4b; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎧 {store_name}</h1>
        
        <div class="current-box">
            <div id="status" style="font-size:0.8em; color:#666;">停止中</div>
            <div id="track-title" class="current-title">読み込み中...</div>
        </div>

        <audio id="audio-player"></audio>

        <div class="controls">
            <button onclick="prev()">⏮ 前へ</button>
            <button onclick="toggle()" id="play-btn">▶ 再生</button>
            <button onclick="next()">次へ ⏭</button>
        </div>

        <div style="text-align:center; margin-bottom:15px; color:#666;">
            速度: <select id="speed" onchange="changeSpeed()">
                <option value="1.0">1.0倍</option>
                <option value="1.2">1.2倍</option>
                <option value="1.4" selected>1.4倍</option>
                <option value="2.0">2.0倍</option>
            </select>
        </div>

        <div id="playlist" class="list-area"></div>
    </div>

    <script>
        const playlist = {playlist_json_str};
        let idx = 0;
        const audio = document.getElementById('audio-player');
        const titleEl = document.getElementById('track-title');
        const statusEl = document.getElementById('status');
        const btn = document.getElementById('play-btn');

        function init() {{
            renderList();
            load(0);
            changeSpeed();
        }}

        function load(i) {{
            idx = i;
            audio.src = playlist[idx].src;
            titleEl.textContent = playlist[idx].title;
            statusEl.textContent = (idx + 1) + " / " + playlist.length;
            renderList();
            changeSpeed();
        }}

        function toggle() {{
            if (audio.paused) {{
                audio.play();
                btn.textContent = "⏸ 停止";
            }} else {{
                audio.pause();
                btn.textContent = "▶ 再生";
            }}
        }}

        function next() {{
            if (idx < playlist.length - 1) {{
                load(idx + 1);
                audio.play();
                btn.textContent = "⏸ 停止";
            }}
        }}

        function prev() {{
            if (idx > 0) {{
                load(idx - 1);
                audio.play();
                btn.textContent = "⏸ 停止";
            }}
        }}

        function changeSpeed() {{
            audio.playbackRate = parseFloat(document.getElementById('speed').value);
        }}

        // 自動連続再生
        audio.onended = function() {{
            if (idx < playlist.length - 1) {{
                next();
            }} else {{
                btn.textContent = "▶ 再生";
            }}
        }};

        function renderList() {{
            const div = document.getElementById('playlist');
            div.innerHTML = "";
            playlist.forEach((t, i) => {{
                const item = document.createElement('div');
                item.className = "track-item" + (i === idx ? " active" : "");
                item.textContent = (i+1) + ". " + t.title;
                item.onclick = () => {{ load(i); audio.play(); btn.textContent="⏸ 停止"; }};
                div.appendChild(item);
            }});
        }}

        init();
    </script>
</body>
</html>
    """
    return html_content

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
        except: pass
    
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
    
    speed_options = {"標準": "+0%", "少し速く": "+20%", "サクサク (1.4倍)": "+40%", "爆速": "+100%"}
    selected_speed_label = st.selectbox("読み上げ速度", list(speed_options.keys()), index=2)
    rate_value = speed_options[selected_speed_label]

# ==========================================
# 3. メイン画面レイアウト
# ==========================================
st.title("🎧 Menu Player Generator")
st.markdown("##### 視覚障害のある方のための「聴くメニュー」生成アプリ")

# Session State
if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# Step 1
st.markdown("### 1. お店情報の入力")
col1, col2 = st.columns(2)
with col1: store_name = st.text_input("🏠 店舗名（必須）", placeholder="例：カフェタナカ")
with col2: menu_title = st.text_input("📖 今回のメニュー名", placeholder="例：ランチ")

st.markdown("---")
st.markdown("### 2. メニューの登録方法を選ぶ")

input_method = st.radio("方法を選択", ("📂 アルバムから", "📷 その場で撮影", "🌐 URL入力"), horizontal=True)

final_image_list = []
target_url = None

if input_method == "📂 アルバムから":
    uploaded_files = st.file_uploader("写真を選択", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    if uploaded_files: final_image_list.extend(uploaded_files)

elif input_method == "📷 その場で撮影":
    if not st.session_state.show_camera:
        if st.button("📷 カメラ起動", type="primary"):
            st.session_state.show_camera = True
            st.rerun()
    else:
        if st.button("❌ 閉じる"):
            st.session_state.show_camera = False
            st.rerun()
        st.write("▼ 撮影後「追加」を押してください")
        camera_file = st.camera_input("撮影", key=f"camera_{st.session_state.camera_key}")
        if camera_file:
            if st.button("⬇️ 追加して次へ", type="primary"):
                st.session_state.captured_images.append(camera_file)
                st.session_state.camera_key += 1
                st.rerun()
    
    if st.session_state.captured_images:
        final_image_list.extend(st.session_state.captured_images)
        if st.button("🗑️ クリア"):
            st.session_state.captured_images = []
            st.rerun()

elif input_method == "🌐 URL入力":
    target_url = st.text_input("URL", placeholder="https://...")

# Preview
if final_image_list:
    st.markdown("###### ▼ 画像確認")
    cols = st.columns(len(final_image_list))
    for idx, img in enumerate(final_image_list):
        if idx < 5:
            with cols[idx]: st.image(img, caption=f"No.{idx+1}", use_container_width=True)

st.markdown("---")

# Logic
async def generate_audio_safe(text, filename, voice_code, rate_value):
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice_code, rate=rate_value)
            await comm.save(filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0: return "EdgeTTS"
        except Exception: time.sleep(1)
    try:
        tts = gTTS(text=text, lang='ja')
        tts.save(filename)
        return "GoogleTTS"
    except: return "Error"

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").replace("　", "_")

def fetch_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style", "header", "footer", "nav"]): script.extract()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except: return None

# Step 3
st.markdown("### 3. 音声メニューの作成")

if st.button("🎙️ 作成開始", type="primary", use_container_width=True):
    if not api_key or not target_model_name:
        st.error("設定を確認してください")
        st.stop()
    if not store_name:
        st.warning("店舗名を入力してください")
        st.stop()
    if not (final_image_list or target_url):
        st.warning("画像かURLを入力してください")
        st.stop()

    output_dir = os.path.abspath("menu_audio_album")
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    with st.spinner('解析中...'):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            content_parts = []
            
            base_prompt = """
            あなたは視覚障害者のためのレストランメニュー読み上げデータ作成のプロです。
            以下のJSON形式のみを出力してください。Markdown不要。
            接続詞や挨拶は削除し、商品名と価格のみにしてください。
            
            出力例:
            [{"title": "前菜", "text": "シーザーサラダ、800円。"}, {"title": "飯類", "text": "チャーハン、900円。"}]
            """
            
            if final_image_list:
                content_parts.append(base_prompt)
                for f in final_image_list:
                    f.seek(0)
                    content_parts.append({"mime_type": f.type if hasattr(f, 'type') else 'image/jpeg', "data": f.getvalue()})
            elif target_url:
                web_text = fetch_text_from_url(target_url)
                if not web_text: st.error("URLエラー"); st.stop()
                content_parts.append(base_prompt + f"\n\n{web_text[:30000]}")

            # AI Call
            response = None
            for _ in range(3):
                try:
                    response = model.generate_content(content_parts)
                    break
                except exceptions.ResourceExhausted: time.sleep(5)
                except: pass

            if not response: st.error("失敗しました"); st.stop()

            text_resp = response.text
            start = text_resp.find('[')
            end = text_resp.rfind(']') + 1
            if start == -1: st.error("解析エラー"); st.stop()
            menu_data = json.loads(text_resp[start:end])

            # Intro
            intro_title = "はじめに・目次"
            intro_text = f"こんにちは、{store_name}です。"
            if menu_title: intro_text += f"ただいまより{menu_title}をご紹介します。"
            intro_text += "目次です。"
            for i, track in enumerate(menu_data): intro_text += f"{i+2}、{track['title']}。"
            intro_text += "それでは、ごゆっくりお聴きください。"
            menu_data.insert(0, {"title": intro_title, "text": intro_text})

            # Audio Gen
            generated_tracks = []
            progress_bar = st.progress(0)
            
            for i, track in enumerate(menu_data):
                safe_title = sanitize_filename(track['title'])
                filename = f"{i+1:02}_{safe_title}.mp3"
                save_path = os.path.join(output_dir, filename)
                
                speech_text = track['text']
                if i > 0: speech_text = f"{i+1}、{track['title']}。\n{track['text']}"
                
                asyncio.run(generate_audio_safe(speech_text, save_path, voice_code, rate_value))
                generated_tracks.append({"title": track['title'], "path": save_path})
                progress_bar.progress((i + 1) / len(menu_data))

            # HTML Player生成
            html_string = create_standalone_html_player(store_name, generated_tracks)
            
            # ZIP生成
            date_str = datetime.now().strftime('%Y%m%d')
            safe_name = sanitize_filename(store_name)
            zip_filename = f"{safe_name}_{date_str}.zip"
            zip_path = os.path.abspath(zip_filename)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(output_dir):
                    for file in files: zipf.write(os.path.join(root, file), file)

            st.session_state.generated_result = {
                "zip_path": zip_path, "zip_name": zip_filename, 
                "html_content": html_string, "html_name": f"{safe_name}_player.html",
                "tracks": generated_tracks
            }
            st.balloons()

        except Exception as e:
            st.error("エラー"); st.write(e)

# ==========================================
# 4. 結果画面（HTMLダウンロードボタン追加）
# ==========================================
if st.session_state.generated_result:
    res = st.session_state.generated_result
    st.divider()
    st.markdown("## 🎉 完成！")
    
    st.info("スマホの方には「Webプレイヤー」がおすすめです。")

    col_web, col_zip = st.columns(2)
    
    with col_web:
        st.markdown("### 📱 Webプレイヤー")
        st.write("このファイルを送るだけで、アプリなしで再生できます。")
        st.download_button(
            label=f"🌐 {res['html_name']} を保存",
            data=res['html_content'],
            file_name=res['html_name'],
            mime="text/html",
            type="primary"
        )
    
    with col_zip:
        st.markdown("### 🗂 ZIPファイル")
        st.write("PCでの管理用")
        with open(res["zip_path"], "rb") as fp:
            st.download_button(
                label=f"📦 {res['zip_name']} を保存",
                data=fp,
                file_name=res['zip_name'],
                mime="application/zip"
            )

    st.divider()
    st.subheader("▶️ プレビュー再生")
    for track in res["tracks"]:
        st.markdown(f"**{os.path.basename(track['path'])}**")
        if os.path.exists(track['path']): st.audio(track['path'])
