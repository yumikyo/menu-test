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

# 非同期処理の適用
nest_asyncio.apply()

# ページ設定
st.set_page_config(page_title="Runwith Menu AI Generator", layout="wide")

# CSSでボタンのスタイル調整
st.markdown("""
<style>
    div[data-testid="column"] { margin-bottom: 10px; }
    .stButton>button { font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 辞書ファイルの管理 ---
DICT_FILE = "my_dictionary.json"

def load_dictionary():
    if os.path.exists(DICT_FILE):
        with open(DICT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_dictionary(new_dict):
    with open(DICT_FILE, "w", encoding="utf-8") as f:
        json.dump(new_dict, f, ensure_ascii=False, indent=2)

# --- 関数定義 ---
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").replace("　", "_")

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
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True
        except:
            await asyncio.sleep(1)
    try:
        def gtts_task():
            tts = gTTS(text=text, lang='ja')
            tts.save(filename)
        await asyncio.to_thread(gtts_task)
        return True
    except:
        return False

async def process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar):
    tasks = []
    track_info_list = []
    
    for i, track in enumerate(menu_data):
        safe_title = sanitize_filename(track['title'])
        filename = f"{i:02}_{safe_title}.mp3"
        save_path = os.path.join(output_dir, filename)
        speech_text = track['text']
        
        if i > 0: 
             speech_text = f"次は、{track['title']}です。\n{track['text']}"
             
        tasks.append(generate_single_track_fast(speech_text, save_path, voice_code, rate_value))
        track_info_list.append({"title": track['title'], "path": save_path})
    
    total = len(tasks)
    completed = 0
    for task in asyncio.as_completed(tasks):
        await task
        completed += 1
        progress_bar.progress(completed / total)
    return track_info_list

# ★Runwithブランドカラー対応 HTMLプレイヤー生成★
def create_standalone_html_player(store_name, menu_data, map_url=""):
    playlist_js = []
    for track in menu_data:
        file_path = track['path']
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()
                playlist_js.append({"title": track['title'], "src": f"data:audio/mp3;base64,{b64_data}"})
    playlist_json_str = json.dumps(playlist_js, ensure_ascii=False)
    
    map_button_html = ""
    if map_url:
        map_button_html = f"""
        <div style="text-align:center; margin-bottom: 20px;">
            <a href="{map_url}" target="_blank" role="button" aria-label="Googleマップを開く" class="map-btn">
                🗺️ 地図を開く
            </a>
        </div>
        """

    html_template = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>__STORE_NAME__ 音声ガイド</title>
<style>
/* Runwithブランドカラー設定 */
:root {
    --bg-navy: #001F3F;      /* 背景：紺 */
    --text-orange: #FF851B;  /* 文字：明るいオレンジ */
    --accent-white: #FFFFFF; /* アクセント：白 */
}

body {
    font-family: "Helvetica", "Arial", sans-serif;
    background: var(--bg-navy);
    color: var(--text-orange);
    margin: 0;
    padding: 15px;
    line-height: 1.8;
}

.c { max-width: 600px; margin: 0 auto; }

h1 {
    text-align: center;
    font-size: 1.8em;
    color: var(--text-orange);
    border-bottom: 2px solid var(--text-orange);
    padding-bottom: 10px;
}
h2 {
    font-size: 1.4em;
    color: var(--accent-white); /* 見出しは見やすく白で */
    margin-top: 30px;
    border-left: 8px solid var(--text-orange);
    padding-left: 10px;
}

/* 再生中のタイトル表示エリア（枠線オレンジ、中身は紺） */
.box {
    background: var(--bg-navy);
    border: 4px solid var(--text-orange);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    margin-bottom: 20px;
    min-height: 80px;
    display: flex; align-items: center; justify-content: center;
}
.ti { font-size: 1.6em; font-weight: bold; color: var(--text-orange); }

/* 操作ボタン（逆パターン：背景オレンジ、文字紺） */
.ctrl { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px; }
.play-btn-area { grid-column: 1 / -1; margin-bottom: 10px; }

button {
    width: 100%;
    padding: 20px 0;
    font-size: 2em; 
    font-weight: bold;
    color: var(--bg-navy);     /* 文字は紺 */
    background: var(--text-orange); /* 背景はオレンジ */
    border: 2px solid var(--accent-white);
    border-radius: 12px; 
    cursor: pointer;
    touch-action: manipulation;
}
button:active { opacity: 0.8; transform: translateY(2px); }
button:focus { outline: 4px solid var(--accent-white); outline-offset: 4px; }

/* 地図ボタン（特別色：白背景に紺文字） */
.map-btn {
    display: block; width: 100%; padding: 20px; 
    background-color: var(--accent-white); color: var(--bg-navy); 
    text-decoration: none; border-radius: 12px; font-size: 1.4em; font-weight: bold;
    border: 2px solid var(--text-orange); box-sizing: border-box; text-align: center;
}

/* リスト表示 */
.lst { border-top: 2px solid var(--text-orange); margin-top: 20px; }
.itm {
    padding: 20px 10px; 
    border-bottom: 1px solid #555; 
    cursor: pointer; font-size: 1.3em; color: var(--accent-white);
}
/* アクティブな項目（逆パターン：背景薄オレンジ、文字紺） */
.itm.active {
    background: var(--text-orange); 
    color: var(--bg-navy); 
    font-weight: bold; 
    border-left: 10px solid var(--accent-white);
}
</style></head>
<body>
<main class="c" role="main">
    <h1>🎧 __STORE_NAME__</h1>
    __MAP_BUTTON__
    
    <section aria-label="再生内容">
        <div class="box"><div class="ti" id="ti" aria-live="polite">準備中...</div></div>
    </section>

    <audio id="au" style="width:1px;height:1px;opacity:0;"></audio>

    <section aria-label="操作パネル">
        <div class="play-btn-area">
            <button onclick="toggle()" id="pb" aria-label="再生・一時停止">▶ 再生</button>
        </div>
        <div class="ctrl">
            <button onclick="prev()" aria-label="前の項目">⏮ 前</button>
            <button onclick="next()" aria-label="次の項目">次 ⏭</button>
        </div>
    </section>

    <div style="text-align:center; margin:20px 0;">
        <label for="sp" style="font-size:1.2em; color:#FFF;">話す速さ: </label>
        <select id="sp" onchange="csp()" style="font-size:1.2em; padding:10px; border-radius:8px;">
            <option value="0.8">0.8 (ゆっくり)</option>
            <option value="1.0" selected>1.0 (標準)</option>
            <option value="1.2">1.2 (せっかち)</option>
            <option value="1.5">1.5 (爆速)</option>
        </select>
    </div>

    <h2>📜 メニュー一覧</h2>
    <div id="ls" class="lst" role="list"></div>
</main>

<script>
const pl=__PLAYLIST_JSON__;let idx=0;
const au=document.getElementById('au');
const ti=document.getElementById('ti');
const pb=document.getElementById('pb');

function init(){ren();ld(0);csp();}
function ld(i){
    idx=i;
    au.src=pl[idx].src;
    ti.innerText=pl[idx].title;
    ren();
}
function toggle(){
    if(au.paused){
        au.play();
        pb.innerText="⏸ 一時停止";
    }else{
        au.pause();
        pb.innerText="▶ 再生";
    }
}
function next(){
    if(idx<pl.length-1){ ld(idx+1); au.play(); pb.innerText="⏸ 一時停止"; }
}
function prev(){
    if(idx>0){ ld(idx-1); au.play(); pb.innerText="⏸ 一時停止"; }
}
function csp(){au.playbackRate=parseFloat(document.getElementById('sp').value);}
au.onended=function(){
    if(idx<pl.length-1){ next(); }
    else { pb.innerText="▶ 最初に戻る"; idx=0; ld(0); au.pause(); }
};
function ren(){
    const d=document.getElementById('ls');
    d.innerHTML="";
    pl.forEach((t,i)=>{
        const m=document.createElement('div');
        m.className="itm "+(i===idx?"active":"");
        m.setAttribute("role", "listitem");
        m.setAttribute("tabindex", "0");
        let label = t.title;
        if(i > 0){ label = i + ". " + t.title; }
        m.innerText=label;
        m.onclick=()=>{ld(i);au.play();pb.innerText="⏸ 一時停止";};
        d.appendChild(m);
    });
}
init();
</script></body></html>"""

    final_html = html_template.replace("__STORE_NAME__", store_name)
    final_html = final_html.replace("__PLAYLIST_JSON__", playlist_json_str)
    final_html = final_html.replace("__MAP_BUTTON__", map_button_html)
    return final_html

# プレビュー用プレイヤー
def render_preview_player(tracks):
    playlist_data = []
    for track in tracks:
        if os.path.exists(track['path']):
            with open(track['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                playlist_data.append({"title": track['title'],"src": f"data:audio/mp3;base64,{b64}"})
    playlist_json = json.dumps(playlist_data)
    
    html_template = """<!DOCTYPE html><html><head><style>
    body{margin:0;padding:0;font-family:sans-serif;}
    .p-box{border:2px solid #e0e0e0;border-radius:12px;padding:15px;background:#fcfcfc;text-align:center;}
    .t-ti{font-size:18px;font-weight:bold;color:#001F3F;margin-bottom:10px;padding:10px;background:#fff;border-radius:8px;border-left:5px solid #FF851B;}
    .ctrls{display:flex; gap:10px; margin:15px 0;}
    button {
        flex: 1;
        background-color: #001F3F; color: #FF851B; border: none;
        border-radius: 8px; font-size: 24px; padding: 10px 0;
        cursor: pointer; line-height: 1; min-height: 50px;
    }
    button:hover { background-color: #003366; }
    button:focus { outline: 3px solid #333; outline-offset: 2px; }
    .lst{text-align:left;max-height:150px;overflow-y:auto;border-top:1px solid #eee;margin-top:10px;padding-top:5px;}
    .it{padding:8px;border-bottom:1px solid #eee;cursor:pointer;font-size:14px;}
    .it:focus{outline:2px solid #333; background:#eee;}
    .it.active{color:#FF851B;font-weight:bold;background:#001F3F;}
    </style></head><body><div class="p-box"><div id="ti" class="t-ti">...</div><audio id="au" controls style="width:100%;height:30px;"></audio>
    <div class="ctrls">
        <button onclick="pv()" aria-label="前へ">⏮</button>
        <button onclick="tg()" id="pb" aria-label="再生">▶</button>
        <button onclick="nx()" aria-label="次へ">⏭</button>
    </div>
    <div style="font-size:12px;color:#666; margin-top:5px;">
        速度:<select id="sp" onchange="sp()"><option value="0.8">0.8</option><option value="1.0" selected>1.0</option><option value="1.2">1.2</option><option value="1.5">1.5</option></select>
    </div>
    <div id="ls" class="lst" role="list"></div></div>
    <script>
    const pl=__PLAYLIST__;let x=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');const ls=document.getElementById('ls');
    function init(){rn();ld(0);sp();}
    function ld(i){x=i;au.src=pl[x].src;ti.innerText=pl[x].title;rn();sp();}
    function tg(){if(au.paused){au.play();pb.innerText="⏸";pb.setAttribute("aria-label","一時停止");}else{au.pause();pb.innerText="▶";pb.setAttribute("aria-label","再生");}}
    function nx(){if(x<pl.length-1){ld(x+1);au.play();pb.innerText="⏸";pb.setAttribute("aria-label","一時停止");}}
    function pv(){if(x>0){ld(x-1);au.play();pb.innerText="⏸";pb.setAttribute("aria-label","一時停止");}}
    function sp(){au.playbackRate=parseFloat(document.getElementById('sp').value);}
    au.onended=function(){if(x<pl.length-1)nx();else{pb.innerText="▶";pb.setAttribute("aria-label","再生");}};
    function rn(){ls.innerHTML="";pl.forEach((t,i)=>{
        const d=document.createElement('div');
        d.className="it "+(i===x?"active":"");
        let l=t.title; if(i>0){l=i+". "+t.title;}
        d.innerText=l;
        d.setAttribute("role","listitem");d.setAttribute("tabindex","0");d.onclick=()=>{ld(i);au.play();pb.innerText="⏸";pb.setAttribute("aria-label","一時停止");};d.onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();d.click();}};ls.appendChild(d);});}
    init();</script></body></html>"""
    
    final_html = html_template.replace("__PLAYLIST__", playlist_json)
    components.html(final_html, height=450)

# --- UI ---
with st.sidebar:
    st.header("🔧 Runwith 設定")
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
            default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n), 0)
            target_model_name = st.selectbox("使用するAIモデル", valid_models, index=default_idx)
        except: pass
    
    st.divider()
    st.subheader("🗣️ 音声設定")
    voice_options = {"女性（七海）": "ja-JP-NanamiNeural", "男性（慶太）": "ja-JP-KeitaNeural"}
    selected_voice = st.selectbox("声の種類", list(voice_options.keys()))
    voice_code = voice_options[selected_voice]
    rate_value = "+10%"

    # 辞書機能
    st.divider()
    st.subheader("📖 辞書登録")
    st.caption("よく間違える読み方を登録してください。")
    user_dict = load_dictionary()
    
    with st.form("dict_form", clear_on_submit=True):
        c_word, c_read = st.columns(2)
        new_word = c_word.text_input("単語", placeholder="例: 辛口")
        new_read = c_read.text_input("読み", placeholder="例: からくち")
        if st.form_submit_button("➕ 追加"):
            if new_word and new_read:
                user_dict[new_word] = new_read
                save_dictionary(user_dict)
                st.success(f"「{new_word}」を登録しました！")
                st.rerun()

    if user_dict:
        with st.expander(f"登録済み単語 ({len(user_dict)})"):
            for word, read in list(user_dict.items()):
                c1, c2 = st.columns([3, 1])
                c1.text(f"{word} ➡ {read}")
                if c2.button("🗑️", key=f"del_{word}"):
                    del user_dict[word]
                    save_dictionary(user_dict)
                    st.rerun()

st.title("🎧 Runwith Menu AI")
st.caption("Powered by Runwith AI - 伴走型音声メニュー作成ツール")

# State管理
if 'retake_index' not in st.session_state: st.session_state.retake_index = None
if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# Step 1
st.markdown("### 1. お店情報の入力")
c1, c2 = st.columns(2)
with c1: store_name = st.text_input("🏠 店舗名（必須）", placeholder="例：カフェタナカ")
with c2: menu_title = st.text_input("📖 今回のメニュー名 （任意）", placeholder="例：ランチ")

map_url = st.text_input("📍 GoogleマップのURL（任意）", placeholder="例：https://maps.app.goo.gl/...")
if map_url:
    st.caption("※プレイヤーに地図へのアクセスボタンが表示されます。")

st.markdown("---")

st.markdown("### 2. メニューの登録")
input_method = st.radio("方法", ("📂 アルバムから", "📷 その場で撮影", "🌐 URL入力"), horizontal=True)

final_image_list = []
target_url = None

if input_method == "📂 アルバムから":
    uploaded_files = st.file_uploader("写真を選択", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    if uploaded_files: final_image_list.extend(uploaded_files)

elif input_method == "📷 その場で撮影":
    if st.session_state.retake_index is not None:
        target_idx = st.session_state.retake_index
        st.warning(f"No.{target_idx + 1} の画像を再撮影中...")
        retake_camera_key = f"retake_camera_{target_idx}_{st.session_state.camera_key}"
        camera_file = st.camera_input("写真を撮影する (取り直し)", key=retake_camera_key)
        
        c1, c2 = st.columns(2, gap="large")
        with c1:
            if camera_file and st.button("✅ これで決定", type="primary", key="retake_confirm", use_container_width=True):
                st.session_state.captured_images[target_idx] = camera_file
                st.session_state.retake_index = None
                st.session_state.show_camera = False 
                st.session_state.camera_key += 1
                st.rerun()
        with c2:
            if st.button("❌ キャンセル", key="retake_cancel", use_container_width=True):
                st.session_state.retake_index = None
                st.session_state.show_camera = False
                st.rerun()

    elif not st.session_state.show_camera:
        if st.button("📷 カメラ起動", type="primary"):
            st.session_state.show_camera = True
            st.rerun()
    else:
        camera_file = st.camera_input("写真を撮影する", key=f"camera_{st.session_state.camera_key}")
        if camera_file:
            c_btn1, c_btn2 = st.columns(2, gap="large")
            with c_btn1:
                if st.button("⬇️ 追加して次を撮る", type="primary", use_container_width=True):
                    st.session_state.captured_images.append(camera_file)
                    st.session_state.camera_key += 1
                    st.rerun()
            with c_btn2:
                if st.button("✅ 追加して終了", type="primary", use_container_width=True):
                    st.session_state.captured_images.append(camera_file)
                    st.session_state.show_camera = False
                    st.session_state.camera_key += 1
                    st.rerun()
        else:
            if st.button("❌ 撮影を中止", use_container_width=True):
                st.session_state.show_camera = False
                st.rerun()
            
    if st.session_state.captured_images:
        if st.session_state.retake_index is None and st.session_state.show_camera is False:
             if st.button("🗑️ 全て削除"):
                st.session_state.captured_images = []
                st.rerun()
        final_image_list.extend(st.session_state.captured_images)

elif input_method == "🌐 URL入力":
    target_url = st.text_input("URL", placeholder="https://...")

if final_image_list and st.session_state.retake_index is None:
    st.markdown("###### ▼ 画像確認")
    cols_per_row = 3
    for i in range(0, len(final_image_list), cols_per_row):
        cols = st.columns(cols_per_row, gap="medium")
        batch = final_image_list[i:i+cols_per_row]
        for j, img in enumerate(batch):
            global_idx = i + j
            with cols[j]:
                st.image(img, caption=f"No.{global_idx+1}", use_container_width=True)
                if input_method == "📷 その場で撮影" and img in st.session_state.captured_images:
                    c_retake, c_delete = st.columns(2, gap="small")
                    with c_retake:
                        if st.button("🔄 撮り直す", key=f"btn_retake_{global_idx}", use_container_width=True):
                            st.session_state.retake_index = global_idx
                            st.session_state.show_camera = True
                            st.rerun()
                    with c_delete:
                        if st.button("🗑️ 削除", key=f"btn_delete_{global_idx}", use_container_width=True):
                            st.session_state.captured_images.pop(global_idx)
                            st.session_state.retake_index = None
                            st.session_state.show_camera = False
                            st.rerun()

st.markdown("---")

st.markdown("### 3. 音声メニューの作成")
disable_create = st.session_state.retake_index is not None
if st.button("🎙️ 作成開始", type="primary", use_container_width=True, disabled=disable_create):
    if not (api_key and target_model_name and store_name):
        st.error("設定や店舗名を確認してください"); st.stop()
    if not (final_image_list or target_url):
        st.warning("画像かURLを入力してください"); st.stop()

    output_dir = os.path.abspath("menu_audio_album")
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    with st.spinner('Runwith Menu AI が解析中...'):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            parts = []
            
            user_dict_str = json.dumps(user_dict, ensure_ascii=False)
            
            prompt = f"""
            役割設定:
            あなたは視覚障害者の外食をサポートするパートナー「Runwith Menu AI」です。
            メニュー画像を解析し、ユーザーが料理を選びやすいように整理してガイドしてください。

            重要ミッション:
            1. メニュー全体を【5つ〜8つ程度の論理的なチャプター（カテゴリー）】に分けてください。
               （悪い例：各商品を1つのチャプターにする）
               （良い例：「前菜」「メイン」「ドリンク」のようにまとめる）
            
            2. 読み上げ原稿のルール:
               - 各チャプターの冒頭で「次は〇〇のメニューです」とガイドを入れる。
               - 商品名ははっきりと。価格は必ず「円」をつけて読む。
               - 写真から「美味しそうな特徴（赤くて辛そう、ボリュームがある等）」が分かれば、一言添えて魅力を伝える。
               - アレルギー情報や注意事項は絶対に省略しない。

            ★最重要：以下の固有名詞・読み方辞書を必ず守ってください。
            {user_dict_str}

            出力フォーマット（JSONのみ）:
            [
              {{"title": "カテゴリー名（例：おすすめ・フェア）", "text": "まずは、今月のおすすめメニューです。旬のいちごパフェ、1200円。写真では山盛りのイチゴが乗っていてとても豪華です。"}},
              {{"title": "カテゴリー名（例：メイン料理）", "text": "続いてメイン料理です。ハンバーグ定食1000円。ステーキ1500円..."}}
            ]
            """
            
            if final_image_list:
                parts.append(prompt)
                for f in final_image_list:
                    f.seek(0)
                    parts.append({"mime_type": f.type if hasattr(f, 'type') else 'image/jpeg', "data": f.getvalue()})
            elif target_url:
                web_text = fetch_text_from_url(target_url)
                if not web_text: st.error("URLエラー"); st.stop()
                parts.append(prompt + f"\n\n{web_text[:30000]}")

            resp = None
            for _ in range(3):
                try: resp = model.generate_content(parts); break
                except exceptions.ResourceExhausted: time.sleep(5)
                except: pass

            if not resp: st.error("失敗しました"); st.stop()

            text_resp = resp.text
            start = text_resp.find('[')
            end = text_resp.rfind(']') + 1
            if start == -1: st.error("解析エラー"); st.stop()
            menu_data = json.loads(text_resp[start:end])

            intro_t = f"こんにちは、{store_name}へようこそ。Runwith Menu AI がご案内します。"
            if menu_title: intro_t += f"ただいまより{menu_title}をご紹介します。"
            intro_t += "このプレイヤーは、スクリーンリーダーでの操作に対応しています。"
            intro_t += f"このメニューは、全部で{len(menu_data)}つのチャプターに分かれています。まずは目次です。"
            
            for i, tr in enumerate(menu_data): 
                intro_t += f"{i+1}、{tr['title']}。"
                
            intro_t += "それでは、ごゆっくりお選びください。"
            menu_data.insert(0, {"title": "はじめに・目次", "text": intro_t})

            progress_bar = st.progress(0)
            st.info("音声を生成しています... (並列処理中)")
            generated_tracks = asyncio.run(process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar))

            html_str = create_standalone_html_player(store_name, generated_tracks, map_url)
            
            d_str = datetime.now().strftime('%Y%m%d')
            s_name = sanitize_filename(store_name)
            zip_name = f"{s_name}_{d_str}.zip"
            zip_path = os.path.abspath(zip_name)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
                for root, dirs, files in os.walk(output_dir):
                    for file in files: z.write(os.path.join(root, file), file)

            with open(zip_path, "rb") as f:
                zip_data = f.read()

            st.session_state.generated_result = {
                "zip_data": zip_data,
                "zip_name": zip_name,
                "html_content": html_str, 
                "html_name": f"{s_name}_player.html",
                "tracks": generated_tracks
            }
            st.balloons()
        except Exception as e: st.error(f"エラー: {e}")

if st.session_state.generated_result:
    res = st.session_state.generated_result
    st.divider()
    st.subheader("▶️ プレビュー")
    render_preview_player(res["tracks"])
    st.divider()
    st.subheader("📥 保存")
    
    st.info(
        """
        **Webプレイヤー**：視覚障害の方が見やすい「Runwithカラー（紺×オレンジ）」のプレイヤーです。  
        **ZIPファイル**：PCでの保存や、My Menu Bookへの追加にご利用ください。
        """
    )
    
    c1, c2 = st.columns(2)
    with c1: st.download_button(f"🌐 Webプレイヤー ({res['html_name']})", res['html_content'], res['html_name'], "text/html", type="primary")
    with c2: st.download_button(f"📦 ZIPファイル ({res['zip_name']})", data=res["zip_data"], file_name=res['zip_name'], mime="application/zip")

    # --- 店頭用POP作成機能（白背景×紺文字） ---
    st.markdown("---")
    st.subheader("4. 店頭用QRコード・POP作成")
    st.info("💡 作成した「Webプレイヤー（HTMLファイル）」をお店のホームページなどにアップロードし、そのURLをここに入力してください。店頭に置けるPOPが生成されます。")

    public_url = st.text_input("公開したメニューのURLを入力", placeholder="例：https://www.example.com/menu_player.html")

    if public_url:
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={public_url}"
        
        # POPデザイン（白背景・紺文字・オレンジアクセント）
        pop_html = f"""
        <div style="
            border: 4px solid #001F3F; 
            padding: 30px; 
            background: #FFF; 
            text-align: center; 
            max-width: 400px; 
            margin: 0 auto; 
            font-family: 'Hiragino Kaku Gothic Pro', 'Meiryo', sans-serif;
            box-shadow: 5px 5px 15px rgba(0,0,0,0.2);
            color: #001F3F;
        ">
            <h2 style="color: #001F3F; margin-bottom: 10px; font-size: 24px; border-bottom: 3px solid #FF851B; display:inline-block; padding-bottom:5px;">
                🎧 音声メニュー
            </h2>
            <p style="font-size: 16px; font-weight: bold; margin: 20px 0;">
                視覚に障害のある方へ<br>
                スマホで読み上げメニューが使えます
            </p>
            
            <img src="{qr_api_url}" alt="QR Code" style="width: 180px; height: 180px; margin: 10px auto; border: 2px solid #FF851B; padding:5px;">
            
            <p style="font-size: 14px; color: #001F3F; margin-top: 20px; text-align: left; background: #FFD59E; padding: 15px; border-radius: 8px;">
                <strong>飲食店の方へ：</strong><br>
                音声メニューが必要なお客様がいらした際に、ご自身のスマホでこのQRコードを読み取ってもらってください。
            </p>
            
            <div style="margin-top: 15px; font-weight: bold; font-size: 18px; color: #FF851B;">
                {store_name}
            </div>
        </div>
        """
        
        st.markdown("### ▼ 店頭用POPプレビュー")
        st.caption("この画面をスクリーンショットを撮るか、印刷してご利用ください。")
        components.html(pop_html, height=600, scrolling=True)
