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
import streamlit.components.v1 as components
from PIL import Image

# ----------------------------
# 初期設定
# ----------------------------
nest_asyncio.apply()
st.set_page_config(page_title="Runwith Menu AI", layout="wide", page_icon="🎧")

# ----------------------------
# CSS: デザイン調整
# ----------------------------
st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: 'Helvetica Neue', 'Hiragino Kaku Gothic ProN', 'Meiryo', sans-serif;
        font-size: 18px;
    }
    label {
        font-size: 18px !important;
        font-weight: bold !important;
        color: #FF851B !important;
    }
    .streamlit-expanderHeader {
        font-size: 18px !important;
        font-weight: bold !important;
        background-color: #001F3F;
        color: #FFFFFF !important;
        border-radius: 8px;
    }
    .stButton>button { 
        font-weight: bold; 
        font-size: 20px;
        min-height: 60px;
        border-radius: 12px;
        border: 2px solid #FFFFFF;
    }
    .stButton>button[kind="primary"] {
        background-color: #FF851B;
        color: #001F3F;
        border: 2px solid #001F3F;
    }
    .stAlert {
        font-weight: bold;
        border: 2px solid #FF4136;
        background-color: #ffe6e6;
        color: #cc0000;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 辞書・共通関数
# ----------------------------
DICT_FILE = "my_dictionary.json"

def load_dictionary():
    if os.path.exists(DICT_FILE):
        with open(DICT_FILE, "r", encoding="utf-8") as f: return json.load(f)
    return {}

def save_dictionary(new_dict):
    with open(DICT_FILE, "w", encoding="utf-8") as f: json.dump(new_dict, f, ensure_ascii=False, indent=2)

def sanitize_filename(name): return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").replace("　", "_")

def fetch_text_from_url(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "header", "footer", "nav"]): s.extract()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except: return None

async def generate_single_track_fast(text, filename, voice_code, rate_value):
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice_code, rate=rate_value)
            await comm.save(filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0: return True
        except: await asyncio.sleep(1)
    try:
        def gtts_task(): tts = gTTS(text=text, lang='ja'); tts.save(filename)
        await asyncio.to_thread(gtts_task); return True
    except: return False

async def process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar):
    tasks = []
    track_info_list = []
    for i, track in enumerate(menu_data):
        safe_title = sanitize_filename(track['title'])
        filename = f"{i:02}_{safe_title}.mp3"
        save_path = os.path.join(output_dir, filename)
        speech_text = track['text']
        if i > 0: speech_text = f"{i}、{track['title']}。\n{track['text']}"
        tasks.append(generate_single_track_fast(speech_text, save_path, voice_code, rate_value))
        track_info_list.append({"title": track['title'], "path": save_path})
    total = len(tasks)
    completed = 0
    for task in asyncio.as_completed(tasks):
        await task
        completed += 1
        progress_bar.progress(completed / total)
    return track_info_list

# ----------------------------
# HTML生成関数（安全なreplace方式）
# ----------------------------
def create_standalone_html_player(store_name, menu_data, map_url=""):
    playlist_js = []
    for track in menu_data:
        if os.path.exists(track['path']):
            with open(track['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                playlist_js.append({"title": track['title'], "src": f"data:audio/mp3;base64,{b64}"})
    playlist_json_str = json.dumps(playlist_js, ensure_ascii=False)
    
    map_btn = ""
    if map_url:
        map_btn = f"""<div style="text-align:center;margin-bottom:20px;"><a href="{map_url}" target="_blank" role="button" aria-label="Googleマップを開く" class="map-btn">🗺️ 地図を開く</a></div>"""

    # エラー回避のため、f-stringを使わずに通常の文字列として定義
    html = """<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>__STORE_NAME__ 音声メニュー</title><style>:root{--bg:#001F3F;--or:#FF851B;--wh:#FFFFFF;--dk:#003366;}body{font-family:sans-serif;background:var(--bg);color:var(--or);margin:0;padding:15px;line-height:1.8;font-size:18px;}.c{max-width:600px;margin:0 auto;}h1{text-align:center;color:var(--wh);border-bottom:4px solid var(--or);padding-bottom:15px;}.box{background:var(--dk);border:5px solid var(--or);border-radius:15px;padding:25px;text-align:center;margin-bottom:25px;min-height:90px;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 4px 6px rgba(0,0,0,0.3);}.ti{font-size:1.8em;font-weight:bold;color:var(--or);}.ctrl-group{display:flex;flex-direction:column;gap:20px;margin-bottom:25px;}.main-ctrl{display:grid;grid-template-columns:1fr 1fr;gap:20px;}button{width:100%;padding:25px 0;font-size:1.8em;font-weight:bold;color:var(--bg)!important;background:var(--or)!important;border:3px solid var(--wh);border-radius:15px;cursor:pointer;min-height:80px;}button.reset-btn{font-size:1.3em;background:var(--dk)!important;color:var(--wh)!important;border-color:var(--or);}.map-btn{display:block;width:100%;padding:25px;background-color:var(--wh);color:var(--bg)!important;text-decoration:none;border-radius:15px;font-size:1.6em;font-weight:bold;border:3px solid var(--or);box-sizing:border-box;text-align:center;}.lst{border-top:4px solid var(--or);padding-top:20px;margin-top:25px;}.itm{padding:25px 15px;border-bottom:2px solid #666;cursor:pointer;font-size:1.4em;color:var(--wh);border-radius:10px;}.itm.active{background:var(--or)!important;color:var(--bg)!important;font-weight:bold;border-left:12px solid var(--wh);}</style></head><body><main class="c" role="main"><h1>🎧 __STORE_NAME__</h1>__MAP_BUTTON__<section aria-label="再生操作"><div class="box" onclick="toggle()" role="button" aria-label="再生・一時停止"><div class="ti" id="ti" aria-live="polite">▶ 準備中...</div></div></section><audio id="au" preload="metadata" style="opacity:0;position:absolute;"></audio><section class="ctrl-group"><button onclick="restart()" class="reset-btn">⏮ 最初に戻る</button><button onclick="toggle()" id="pb">▶ 再生</button><div class="main-ctrl"><button onclick="prev()">⏮ 前</button><button onclick="next()">次 ⏭</button></div></section><div style="text-align:center;margin:25px 0;padding:20px;background:var(--dk);border-radius:12px;"><label style="font-size:1.4em;color:var(--wh);">速度:</label><select id="sp" onchange="csp()" style="font-size:1.4em;padding:10px;border-radius:8px;"><option value="0.8">0.8</option><option value="1.0">1.0</option><option value="1.2">1.2</option><option value="1.5">1.5</option></select></div><section><h2>📜 メニュー</h2><div id="ls" class="lst" role="list"></div></section></main><script>const pl=__PLAYLIST_JSON__;let idx=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');function init(){ren();ld(0);csp();upT();}function ld(i){idx=i;au.src=pl[idx].src;upT();ren();csp();}function upT(){const ic=au.paused?"▶":"⏸";ti.innerText=ic+" "+pl[idx].title;}function toggle(){if(au.paused){au.play();pb.innerText="⏸ 一時停止";}else{au.pause();pb.innerText="▶ 再生";}upT();}function restart(){idx=0;ld(0);au.play();pb.innerText="⏸ 一時停止";upT();}function next(){if(idx<pl.length-1){ld(idx+1);au.play();pb.innerText="⏸ 一時停止";}upT();}function prev(){if(idx>0){ld(idx-1);au.play();pb.innerText="⏸ 一時停止";}upT();}function csp(){au.playbackRate=parseFloat(document.getElementById('sp').value);}au.onended=function(){if(idx<pl.length-1){next();}else{pb.innerText="▶ 再生";idx=0;ld(0);au.pause();upT();}};au.onplay=()=>{pb.innerText="⏸ 一時停止";upT();};au.onpause=()=>{pb.innerText="▶ 再生";upT();};function ren(){const d=document.getElementById('ls');d.innerHTML="";pl.forEach((t,i)=>{const m=document.createElement('div');m.className="itm "+(i===idx?"active":"");m.setAttribute("role","listitem");let l=t.title;if(i>0){l=i+". "+t.title;}m.innerText=l;m.onclick=()=>{ld(i);au.play();pb.innerText="⏸ 一時停止";};d.appendChild(m);});}init();</script></body></html>"""
    
    # ここで安全に置換
    html = html.replace("__STORE_NAME__", store_name)
    html = html.replace("__MAP_BUTTON__", map_btn)
    html = html.replace("__PLAYLIST_JSON__", playlist_json_str)
    return html

def render_preview_player(tracks):
    playlist_data = []
    for track in tracks:
        if os.path.exists(track['path']):
            with open(track['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                playlist_data.append({"title": track['title'], "src": f"data:audio/mp3;base64,{b64}"})
    playlist_json = json.dumps(playlist_data)
    
    # 同様にf-stringを避ける
    html = """<!DOCTYPE html><html><head><style>body{margin:0;padding:0;font-family:sans-serif;}.p-box{border:3px solid #001F3F;border-radius:12px;padding:15px;background:#fcfcfc;text-align:center;}.t-ti{font-size:18px;font-weight:bold;color:#001F3F;margin-bottom:10px;padding:10px;background:#fff;border-radius:8px;border-left:5px solid #FF851B;}.ctrls{display:flex;gap:10px;margin:15px 0;}button{flex:1;background-color:#FF851B;color:#001F3F;border:2px solid #001F3F;border-radius:8px;font-size:24px;padding:10px 0;cursor:pointer;font-weight:bold;}button:hover{background-color:#FF6B00;}.lst{text-align:left;max-height:150px;overflow-y:auto;border-top:1px solid #eee;margin-top:10px;padding-top:5px;}.it{padding:8px;border-bottom:1px solid #eee;cursor:pointer;font-size:14px;}.it:focus{outline:2px solid #001F3F;background:#eee;}.it.active{color:#FF851B;font-weight:bold;background:#001F3F;}</style></head><body><div class="p-box"><div id="ti" class="t-ti">...</div><audio id="au" controls style="width:100%;height:30px;"></audio><div class="ctrls"><button onclick="pv()">⏮</button><button onclick="tg()" id="pb">▶</button><button onclick="nx()">⏭</button></div><div id="ls" class="lst"></div></div><script>const pl=__PLAYLIST__;let x=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');const ls=document.getElementById('ls');function init(){rn();ld(0);}function ld(i){x=i;au.src=pl[x].src;ti.innerText=pl[x].title;rn();}function tg(){if(au.paused){au.play();pb.innerText="⏸";}else{au.pause();pb.innerText="▶";}}function nx(){if(x<pl.length-1){ld(x+1);au.play();pb.innerText="⏸";}else{ld(0);au.pause();pb.innerText="▶";}}function pv(){if(x>0){ld(x-1);au.play();pb.innerText="⏸";}else{ld(0);au.pause();pb.innerText="▶";}}au.onended=function(){if(x<pl.length-1)nx();else pb.innerText="▶";};function rn(){ls.innerHTML="";pl.forEach((t,i)=>{const d=document.createElement('div');d.className="it "+(i===x?"active":"");let l=t.title;if(i>0){l=i+". "+t.title;}d.innerText=l;d.onclick=()=>{ld(i);au.play();pb.innerText="⏸";};ls.appendChild(d);});}init();</script></body></html>"""
    html = html.replace("__PLAYLIST__", playlist_json)
    components.html(html, height=450)

# ----------------------------
# UI コンポーネント関数
# ----------------------------

def render_settings_ui(container, key_suffix=""):
    """設定項目を描画する関数"""
    with container:
        st.header("🔧 システム設定")
        
        api_key = None
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
            st.markdown(
                """
                <div style="background-color: #ff9f1c; padding: 10px; border-radius: 5px; margin-bottom: 20px;">
                    <strong style="color: white;">✅ APIキー認証済み</strong>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            api_key = st.text_input("🔑 Gemini APIキー (必須)", type="password", key=f"api_{key_suffix}")
        
        target_model_name = None
        valid_models = []
        if api_key:
            try:
                genai.configure(api_key=api_key)
                all_models = list(genai.list_models())
                valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
                default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n.lower()), 0)
                target_model_name = st.selectbox("🤖 AIモデル", valid_models, index=default_idx, key=f"model_{key_suffix}")
            except:
                pass

        st.markdown("---")
        st.subheader("🗣️ 音声設定")
        
        # 声の種類
        voice_options = {"👩 女性": "ja-JP-NanamiNeural", "👨 男性": "ja-JP-KeitaNeural"}
        selected_v_key = st.radio("声の種類", list(voice_options.keys()), horizontal=True, key=f"voice_{key_suffix}")
        voice_code = voice_options[selected_v_key]
        
        # 読み上げ速度（★ここを追加しました★）
        st.markdown("##### 🚀 読み上げ速度")
        speed_labels = ["ゆっくり", "普通", "やや速い", "速い", "爆速"]
        selected_speed_label = st.select_slider(
            "速度を選択してください",
            options=speed_labels,
            value="やや速い",
            key=f"speed_{key_suffix}"
        )
        # 速度変換マップ
        speed_map = {
            "ゆっくり": "-20%", 
            "普通": "+0%", 
            "やや速い": "+10%", 
            "速い": "+30%", 
            "爆速": "+50%"
        }
        voice_rate = speed_map[selected_speed_label]

        st.markdown("---")
        st.subheader("📝 読み上げモード")
        reading_mode = st.radio(
            "情報の詳しさ", 
            ("💬 シンプル (商品名と価格)", "🌟 詳細 (説明・イメージ付き)"), 
            index=0, 
            key=f"mode_{key_suffix}"
        )

        st.markdown("---")
        st.subheader("📖 読み方辞書")
        user_dict = load_dictionary()
        
        with st.form(key=f"dict_form_{key_suffix}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            nw = c1.text_input("単語", placeholder="例: 辛口")
            nr = c2.text_input("読み", placeholder="例: からくち")
            if st.form_submit_button("➕ 追加"):
                if nw and nr:
                    user_dict[nw] = nr
                    save_dictionary(user_dict)
                    st.success(f"登録: {nw} -> {nr}")
                    st.rerun()
        
        if user_dict:
            with st.expander(f"登録済み単語 ({len(user_dict)})"):
                for w, r in list(user_dict.items()):
                    dc1, dc2 = st.columns([3, 1])
                    dc1.text(f"{w} : {r}")
                    if dc2.button("🗑️", key=f"del_{w}_{key_suffix}"):
                        del user_dict[w]
                        save_dictionary(user_dict)
                        st.rerun()
                        
    return api_key, target_model_name, voice_code, reading_mode, user_dict, voice_rate

# ----------------------------
# メインアプリケーション
# ----------------------------

# State管理
if 'retake_index' not in st.session_state: st.session_state.retake_index = None
if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# タイトルエリア
st.markdown("""
<div style='background: linear-gradient(135deg, #001F3F 0%, #003366 100%); color: #FF851B; padding: 25px; border-radius: 15px; text-align: center; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);'>
    <h1 style='font-size: 2.2em; margin: 0; color: #FFFFFF;'>🎧 Runwith Menu Maker</h1>
    <p style='font-size: 1.2em; margin: 10px 0 0 0; color: #FF851B; font-weight: bold;'>店舗用 音声メニュー作成ツール</p>
</div>
""", unsafe_allow_html=True)

# レイアウト切替スイッチ
layout_mode = st.radio(
    "🖥️ 表示レイアウト", 
    ["💻 PC向け (設定サイドバー)", "📱 モバイル向け (縦一列)"], 
    horizontal=True
)

is_mobile_mode = "モバイル" in layout_mode

# 設定変数の初期化
api_key = None
target_model_name = None
voice_code = "ja-JP-NanamiNeural"
reading_mode = "💬 シンプル (商品名と価格)"
user_dict = {}
voice_rate = "+10%" # 初期値

# --- レイアウト分岐 ---
if not is_mobile_mode:
    # PCモード
    api_key, target_model_name, voice_code, reading_mode, user_dict, voice_rate = render_settings_ui(st.sidebar, "pc")
else:
    # モバイルモード用の変数確保
    pass 

# --- メインコンテンツ ---

# Step 1: お店情報
st.markdown("### 🏪 1. 店舗情報")
col1, col2 = st.columns(2)
with col1: store_name = st.text_input("🏠 店名（必須）", placeholder="例：Runwith Cafe")
with col2: menu_title = st.text_input("📖 メニュー名", placeholder="例：ランチメニュー")
map_url = st.text_input("📍 GoogleマップURL", placeholder="https://goo.gl/maps/...")
st.caption("※プレイヤーに地図ボタンが表示されます。")

st.markdown("---")

# Step 2: 素材登録
st.markdown("### 📸 2. メニュー素材")
input_method = st.radio("入力方法", ("📂 ファイル選択", "📷 カメラ撮影", "🌐 Web URL"), horizontal=True)

final_image_list = []
target_url = None

if input_method == "📂 ファイル選択":
    uploaded_files = st.file_uploader("画像をアップロード", type=['png','jpg','jpeg'], accept_multiple_files=True)
    if uploaded_files: final_image_list.extend(uploaded_files)

elif input_method == "📷 カメラ撮影":
    if st.session_state.retake_index is not None:
        st.warning("再撮影中...")
        cam = st.camera_input("再撮影", key=f"retake_{st.session_state.camera_key}")
        if cam and st.button("決定"):
            st.session_state.captured_images[st.session_state.retake_index] = cam
            st.session_state.retake_index = None
            st.session_state.camera_key += 1; st.rerun()
    else:
        if st.button("📷 カメラを起動"): st.session_state.show_camera = True; st.rerun()
        if st.session_state.show_camera:
            cam = st.camera_input("撮影", key=f"cam_{st.session_state.camera_key}")
            if cam:
                c1, c2 = st.columns(2)
                if c1.button("➕ 次も撮る"): st.session_state.captured_images.append(cam); st.session_state.camera_key += 1; st.rerun()
                if c2.button("✅ 撮影終了"): st.session_state.captured_images.append(cam); st.session_state.show_camera = False; st.rerun()
    if st.session_state.captured_images and st.session_state.retake_index is None:
        if st.button("🗑️ 全削除"): st.session_state.captured_images = []; st.rerun()
        final_image_list.extend(st.session_state.captured_images)

elif input_method == "🌐 Web URL":
    target_url = st.text_input("URL", placeholder="https://...")

if final_image_list and st.session_state.retake_index is None:
    st.markdown("#### ▼ 登録画像")
    cols = st.columns(3)
    for i, img in enumerate(final_image_list):
        with cols[i % 3]:
            st.image(img, caption=f"No.{i+1}", use_column_width=True)
            if input_method == "📷 カメラ撮影":
                c1, c2 = st.columns(2)
                if c1.button("再撮影", key=f"rt_{i}"): st.session_state.retake_index = i; st.rerun()
                if c2.button("削除", key=f"del_{i}"): st.session_state.captured_images.pop(i); st.rerun()

st.markdown("---")

# モバイルモードの場合、ここに設定エリアを配置
if is_mobile_mode:
    with st.expander("⚙️ 設定・辞書 (APIキー・音声設定など)", expanded=False):
        api_key, target_model_name, voice_code, reading_mode, user_dict, voice_rate = render_settings_ui(st.container(), "mobile")

# Step 3: 作成ボタン
st.markdown("### 🚀 3. 作成")
is_retaking = st.session_state.retake_index is not None

if st.button("🎙️ 作成開始 (Runwith AI)", type="primary", disabled=is_retaking, use_container_width=True):
    errors = []
    if not api_key: errors.append("❌ APIキーが設定されていません。")
    if not store_name: errors.append("❌ 店舗名が入力されていません。")
    if not (final_image_list or target_url): errors.append("❌ メニューの画像、またはURLが指定されていません。")
    if api_key and not target_model_name: errors.append("❌ AIモデルが取得できませんでした。APIキーが正しいか確認してください。")

    if errors:
        st.error("以下の理由で作成できませんでした：")
        for e in errors: st.error(e)
    else:
        with st.spinner('AIがメニューを解析して音声を生成中...'):
            output_dir = "menu_audio_temp"
            if os.path.exists(output_dir): shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)

            try:
                # 日付文字列をここで定義
                date_str = datetime.now().strftime('%Y%m%d_%H%M%S')

                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(target_model_name)
                user_dict_str = json.dumps(user_dict, ensure_ascii=False)
                
                prompt = f"""
                視覚障害者向けメニュー読み上げデータ作成。
                【ルール】
                1. メニューを5〜8個の論理的カテゴリー（例：前菜、メイン）に分ける。
                2. 項目ごとにカテゴリーを作らない。
                3. 商品名と価格（円）をテンポよく読む。
                4. アレルギー、辛さ等は省略しない。
                【辞書】{user_dict_str}
                【出力JSON】
                [
                  {{"title": "カテゴリ名", "text": "読み上げ文"}}, ...
                ]
                """
                inputs = [prompt]
                if final_image_list:
                    for f in final_image_list: f.seek(0); inputs.append({"mime_type": f.type if hasattr(f,'type') else 'image/jpeg', "data": f.getvalue()})
                elif target_url:
                    wt = fetch_text_from_url(target_url)
                    inputs.append(wt[:30000] if wt else "")
                
                resp = model.generate_content(inputs)
                match = re.search(r'\[.*\]', resp.text, re.DOTALL)
                if not match: raise Exception("AIからの応答がJSON形式ではありませんでした。")
                menu_data = json.loads(match.group())
                
                intro = f"こんにちは、{store_name}です。"
                if menu_title: intro += f"ただいまより{menu_title}をご紹介します。"
                intro += "全部で{len(menu_data)}つのカテゴリーに分かれています。まずは目次です。"
                for i, tr in enumerate(menu_data): intro += f"{i+1}、{tr['title']}。"
                intro += "それではどうぞ。"
                menu_data.insert(0, {"title": "はじめに・目次", "text": intro})
                
                pbar = st.progress(0)
                
                # ★ここで設定した速度（voice_rate）を使います
                tracks = asyncio.run(process_all_tracks_fast(menu_data, output_dir, voice_code, voice_rate, pbar))
                
                html = create_standalone_html_player(store_name, tracks, map_url)
                
                s_name = sanitize_filename(store_name)
                zip_name = f"Runwith_{s_name}_{date_str}.zip"
                zip_path = os.path.abspath(zip_name)
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z: z.writestr("index.html", html)
                with open(zip_path, "rb") as f: zip_data = f.read()
                
                st.session_state.generated_result = {
                    "tracks": tracks, "html": html, "html_n": f"{s_name}_player.html", 
                    "zip": zip_data, "zip_n": zip_name, "sn": store_name
                }
                st.success("✨ 完成しました！"); st.balloons()
            except Exception as e: st.error(f"エラーが発生しました: {e}")

# Step 4: 結果
if st.session_state.generated_result:
    res = st.session_state.generated_result
    st.markdown("---"); st.markdown("### ▶️ プレビュー")
    render_preview_player(res["tracks"])
    st.markdown("---"); st.markdown("### 📥 保存")
    st.info("Webプレイヤーはスマホ・LINE共有用、ZIPはPC保存用です。")
    c1, c2 = st.columns(2)
    with c1: st.download_button(f"🌐 Webプレイヤー", res['html'], res['html_n'], "text/html", type="primary", use_container_width=True)
    with c2: st.download_button(f"📦 ZIPファイル", res['zip'], res['zip_n'], "application/zip", use_container_width=True)
    
    st.markdown("---"); st.markdown("### 🏪 店頭用POP")
    url = st.text_input("公開URLを入力", key="pop_url")
    if url:
        qr = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url}"
        pop_html = """<div style="border:6px solid #001F3F;padding:30px;background:white;text-align:center;max-width:400px;margin:0 auto;border-radius:20px;color:#001F3F;font-family:sans-serif;"><h2 style="color:#001F3F;border-bottom:4px solid #FF851B;display:inline-block;padding-bottom:5px;">🎧 音声メニュー</h2><p style="font-weight:bold;font-size:18px;">スマホでメニューを読み上げます</p><img src="__QR__" style="width:200px;border:2px solid #ddd;padding:10px;margin:20px 0;"><div style="background:#FFD59E;padding:15px;border-radius:10px;text-align:left;font-size:14px;"><strong>使い方：</strong><br>1. QRコードを読み取る<br>2. 再生ボタンを押す</div><p style="margin-top:15px;font-weight:bold;">__SN__</p></div>"""
        pop_html = pop_html.replace("__QR__", qr).replace("__SN__", res['sn'])
        components.html(pop_html, height=600, scrolling=True)
