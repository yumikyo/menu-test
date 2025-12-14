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

# 非同期処理の適用
nest_asyncio.apply()

# ページ設定
st.set_page_config(page_title="Runwith Menu AI Generator", layout="wide", page_icon="🎧")

# ----------------------------
# CSS: ハイコントラスト & 高齢者対応デザイン (Runwith Brand)
# ----------------------------
st.markdown("""
<style>
    /* 全体のフォント調整 */
    html, body, [class*="css"] {
        font-family: 'Helvetica Neue', 'Hiragino Kaku Gothic ProN', 'Meiryo', sans-serif;
    }
    
    /* ボタンのスタイル強化 */
    .stButton>button { 
        font-weight: bold; 
        font-size: 18px;
        min-height: 60px;
        border-radius: 10px;
        border: 2px solid #FFFFFF;
    }
    
    /* Primaryボタン（アクション） */
    .stButton>button[kind="primary"] {
        background-color: #FF851B;
        color: #001F3F;
        border: 2px solid #001F3F;
    }
    
    /* Secondaryボタン */
    .stButton>button[kind="secondary"] {
        background-color: #001F3F;
        color: #FFFFFF;
        border: 2px solid #FF851B;
    }

    /* 入力ラベルの見やすさ */
    label {
        font-size: 16px !important;
        font-weight: bold !important;
        color: #FF851B !important;
    }
    
    /* 選択肢（ラジオボタン等） */
    .stRadio > div { gap: 20px; }
    .stRadio label { font-size: 18px !important; }
    
    /* Expanderのスタイル */
    .streamlit-expanderHeader {
        color: #FF851B !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------
# 辞書ファイルの管理
# ----------------------------

DICT_FILE = "my_dictionary.json"

def load_dictionary():
    if os.path.exists(DICT_FILE):
        with open(DICT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_dictionary(new_dict):
    with open(DICT_FILE, "w", encoding="utf-8") as f:
        json.dump(new_dict, f, ensure_ascii=False, indent=2)

# ----------------------------
# 共通関数
# ----------------------------

def sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字を安全な形に整形"""
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_").replace("　", "_")

def fetch_text_from_url(url: str) -> str | None:
    """URLから本文テキストを取得"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        for s in soup(["script", "style", "header", "footer", "nav"]):
            s.extract()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception:
        return None

async def generate_single_track_fast(text: str, filename: str, voice_code: str, rate_value: str) -> bool:
    """edge-tts で音声生成。失敗時は gTTS にフォールバック"""
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice_code, rate=rate_value)
            await comm.save(filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True
        except Exception:
            await asyncio.sleep(1)

    try:
        def gtts_task():
            tts = gTTS(text=text, lang='ja')
            tts.save(filename)
        await asyncio.to_thread(gtts_task)
        return True
    except Exception:
        return False

async def process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar):
    """すべてのチャプター音声を並列生成"""
    tasks = []
    track_info_list = []
    
    for i, track in enumerate(menu_data):
        safe_title = sanitize_filename(track['title'])
        filename = f"{i:02}_{safe_title}.mp3"
        save_path = os.path.join(output_dir, filename)
        speech_text = track['text']
        
        if i > 0:
            speech_text = f"{i}、{track['title']}。\n{track['text']}"
            
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
# HTMLプレイヤー生成（JS埋め込み完全版・Runwithデザイン）
# ----------------------------

def create_standalone_html_player(store_name, menu_data, map_url=""):
    """店舗向け配布用のスタンドアロンHTMLプレイヤーを生成"""
    playlist_js = []
    for track in menu_data:
        file_path = track['path']
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode()
                playlist_js.append({
                    "title": track['title'],
                    "src": f"data:audio/mp3;base64,{b64_data}"
                })
    playlist_json_str = json.dumps(playlist_js, ensure_ascii=False)
    
    map_button_html = ""
    if map_url:
        map_button_html = f"""
        <div style="text-align:center; margin-bottom: 20px;">
            <a href="{map_url}" target="_blank" 
               role="button" 
               aria-label="Googleマップを開く（{store_name}の場所）" 
               class="map-btn">
                🗺️ 地図を開く
            </a>
        </div>
        """

    html_template = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__STORE_NAME__ 音声メニュー - Runwith AI</title>
<style>
:root { --bg-navy: #001F3F; --text-orange: #FF851B; --accent-white: #FFFFFF; --bg-dark: #003366; }
body { font-family: sans-serif; background: var(--bg-navy); color: var(--text-orange); margin: 0; padding: 15px; line-height: 1.8; font-size: 18px; }
.c { max-width: 600px; margin: 0 auto; }
h1 { text-align: center; font-size: 2em; color: var(--accent-white); border-bottom: 4px solid var(--text-orange); padding-bottom: 15px; margin-bottom: 25px; }

/* 再生中タイトルエリア（ボタン化） */
.box { 
    background: var(--bg-dark); 
    border: 5px solid var(--text-orange); 
    border-radius: 15px; 
    padding: 25px; 
    text-align: center; 
    margin-bottom: 25px; 
    min-height: 100px; 
    display: flex; 
    align-items: center; 
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    transition: transform 0.1s;
}
.box:active { transform: scale(0.98); }
.box:hover { background-color: #004080; }

.ti { font-size: 1.8em; font-weight: bold; color: var(--text-orange); }
.ctrl-group { display: flex; flex-direction: column; gap: 20px; margin-bottom: 25px; }
.main-ctrl { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
button { width: 100%; padding: 25px 0; font-size: 1.8em; font-weight: bold; color: var(--bg-navy) !important; background: var(--text-orange) !important; border: 3px solid var(--accent-white); border-radius: 15px; cursor: pointer; min-height: 80px; }
button.reset-btn { font-size: 1.3em; background: var(--bg-dark) !important; color: var(--accent-white) !important; border-color: var(--text-orange); }
.map-btn { display: block; width: 100%; padding: 25px; background-color: var(--accent-white); color: var(--bg-navy) !important; text-decoration: none; border-radius: 15px; font-size: 1.6em; font-weight: bold; border: 3px solid var(--text-orange); box-sizing: border-box; text-align: center; }
.lst { border-top: 4px solid var(--text-orange); padding-top: 20px; margin-top: 25px; }
.itm { padding: 25px 15px; border-bottom: 2px solid #666; cursor: pointer; font-size: 1.4em; color: var(--accent-white); border-radius: 10px; margin-bottom: 8px; }
.itm.active { background: var(--text-orange) !important; color: var(--bg-navy) !important; font-weight: bold; border-left: 12px solid var(--accent-white); }
</style>
</head>
<body>
<main class="c" role="main">
    <h1>🎧 __STORE_NAME__</h1>
    __MAP_BUTTON__
    
    <section aria-label="再生状況と操作">
        <div class="box" onclick="toggle()" role="button" aria-label="再生・一時停止">
            <div class="ti" id="ti" aria-live="polite">▶ 準備中...</div>
        </div>
    </section>
    
    <audio id="au" preload="metadata" style="opacity:0;position:absolute;"></audio>
    
    <section class="ctrl-group">
        <button onclick="restart()" class="reset-btn">⏮ 最初に戻る</button>
        <button onclick="toggle()" id="pb">▶ 再生</button>
        <div class="main-ctrl">
            <button onclick="prev()">⏮ 前</button>
            <button onclick="next()">次 ⏭</button>
        </div>
    </section>
    <div style="text-align:center; margin:25px 0; padding:20px; background:var(--bg-dark); border-radius:12px;">
        <label for="sp" style="font-size:1.4em; color:var(--accent-white); font-weight:bold;">話す速さ: </label>
        <select id="sp" onchange="csp()" style="font-size:1.4em; padding:12px; border-radius:10px;">
            <option value="0.8">0.8 (ゆっくり)</option>
            <option value="1.0" selected>1.0 (標準)</option>
            <option value="1.2">1.2 (せっかち)</option>
            <option value="1.5">1.5 (爆速)</option>
        </select>
    </div>
    <section>
        <h2>📜 メニュー一覧</h2>
        <div id="ls" class="lst"></div>
    </section>
</main>
<script>
const pl=__PLAYLIST_JSON__;let idx=0;
const au=document.getElementById('au'); const ti=document.getElementById('ti'); const pb=document.getElementById('pb');

function init(){ ren(); ld(0); csp(); updateTitleUI(); }

function ld(i){ idx=i; au.src=pl[idx].src; updateTitleUI(); ren(); csp(); }

function updateTitleUI() {
    // 再生状態に合わせてアイコンを切り替え
    const icon = au.paused ? "▶" : "⏸";
    ti.innerText = icon + " " + pl[idx].title;
}

function toggle(){ 
    if(au.paused){ 
        au.play(); 
        pb.innerText="⏸ 一時停止"; 
    }else{ 
        au.pause(); 
        pb.innerText="▶ 再生"; 
    } 
    updateTitleUI();
}

function restart(){ idx=0; ld(0); au.play(); pb.innerText="⏸ 一時停止"; updateTitleUI(); }

function next(){ 
    if(idx<pl.length-1){ ld(idx+1); au.play(); pb.innerText="⏸ 一時停止"; }
    updateTitleUI();
}

function prev(){ 
    if(idx>0){ ld(idx-1); au.play(); pb.innerText="⏸ 一時停止"; }
    updateTitleUI();
}

function csp(){ au.playbackRate=parseFloat(document.getElementById('sp').value); }

au.onended=function(){ 
    if(idx<pl.length-1){ next(); } 
    else { pb.innerText="▶ 再生"; idx=0; ld(0); au.pause(); updateTitleUI(); } 
};

au.onplay = function() { pb.innerText="⏸ 一時停止"; updateTitleUI(); };
au.onpause = function() { pb.innerText="▶ 再生"; updateTitleUI(); };

function ren(){
    const d=document.getElementById('ls'); d.innerHTML="";
    pl.forEach((t,i)=>{
        const m=document.createElement('div'); m.className="itm "+(i===idx?"active":"");
        let label = t.title; if(i > 0){ label = i + ". " + t.title; }
        m.innerText=label; 
        m.onclick=()=>{ ld(i); au.play(); pb.innerText="⏸ 一時停止"; };
        d.appendChild(m);
    });
}
init();
</script>
</body>
</html>"""

    final_html = html_template.replace("__STORE_NAME__", store_name)
    final_html = final_html.replace("__PLAYLIST_JSON__", playlist_json_str)
    final_html = final_html.replace("__MAP_BUTTON__", map_button_html)
    return final_html

# ----------------------------
# プレビュー用プレイヤー（改良版・Runwithデザイン）
# ----------------------------

def render_preview_player(tracks):
    playlist_data = []
    for track in tracks:
        if os.path.exists(track['path']):
            with open(track['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                playlist_data.append({
                    "title": track['title'],
                    "src": f"data:audio/mp3;base64,{b64}"
                })
    playlist_json = json.dumps(playlist_data)
    
    html_template = """<!DOCTYPE html><html><head><style>
    body{margin:0;padding:0;font-family:sans-serif;}
    .p-box{border:3px solid #001F3F;border-radius:12px;padding:15px;background:#fcfcfc;text-align:center;}
    .t-ti{font-size:18px;font-weight:bold;color:#001F3F;margin-bottom:10px;padding:10px;background:#fff;border-radius:8px;border-left:5px solid #FF851B;}
    .ctrls{display:flex; gap:10px; margin:15px 0;}
    button {
        flex: 1;
        background-color: #FF851B; color: #001F3F; border: 2px solid #001F3F;
        border-radius: 8px; font-size: 24px; padding: 10px 0;
        cursor: pointer; line-height: 1; min-height: 50px; font-weight: bold;
    }
    button:hover { background-color: #FF6B00; }
    button:focus { outline: 3px solid #001F3F; outline-offset: 2px; }
    .lst{text-align:left;max-height:150px;overflow-y:auto;border-top:1px solid #eee;margin-top:10px;padding-top:5px;}
    .it{padding:8px;border-bottom:1px solid #eee;cursor:pointer;font-size:14px;}
    .it:focus{outline:2px solid #001F3F; background:#eee;}
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

# ----------------------------
# サイドバー（設定）
# ----------------------------

with st.sidebar:
    st.markdown("""
    <div style='background:#001F3F;color:#FF851B;padding:20px;border-radius:15px;text-align:center;font-weight:bold;font-size:18px;'>
        Runwith Menu Maker
    </div>
    """, unsafe_allow_html=True)
    
    st.header("🔧 システム設定")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ APIキー認証済み")
    else:
        api_key = st.text_input("🔑 Gemini APIキー", type="password")
    
    # モデル選択
    valid_models = []
    target_model_name = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            all_models = list(genai.list_models())
            valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
            default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n.lower()), 0)
            target_model_name = st.selectbox("🤖 AIモデル", valid_models, index=default_idx)
        except Exception as e:
            st.error(f"APIエラー: {e}")
    
    st.divider()
    st.header("🗣️ 音声設定")
    # 表示名シンプル化、デフォルト速度+10%
    voice_options = {"👩 女性": "ja-JP-NanamiNeural", "👨 男性": "ja-JP-KeitaNeural"}
    selected_voice = st.radio("声の種類", list(voice_options.keys()), horizontal=True)
    voice_code = voice_options[selected_voice]
    rate_value = "+10%"

    st.divider()
    st.header("📝 読み上げモード")
    reading_mode = st.radio(
        "情報の詳しさ", 
        ("💬 シンプル (商品名と価格)", "🌟 詳細 (説明・イメージ付き)"), 
        index=0
    )

    st.divider()
    st.subheader("📖 読み方辞書")
    st.caption("AIが読み間違える単語を登録してください。")
    
    user_dict = load_dictionary()
    with st.form("dict_form", clear_on_submit=True):
        c_word, c_read = st.columns(2)
        new_word = c_word.text_input("単語", placeholder="例: 辛口")
        new_read = c_read.text_input("読み", placeholder="例: からくち")
        if st.form_submit_button("➕ 追加"):
            if new_word and new_read:
                user_dict[new_word] = new_read
                save_dictionary(user_dict)
                st.success(f"登録: {new_word} -> {new_read}")
                st.rerun()

    if user_dict:
        with st.expander(f"登録済み ({len(user_dict)})"):
            for word, read in list(user_dict.items()):
                c1, c2 = st.columns([3, 1])
                c1.text(f"{word} : {read}")
                if c2.button("🗑️", key=f"del_{word}"):
                    del user_dict[word]
                    save_dictionary(user_dict)
                    st.rerun()

# ----------------------------
# メイン画面
# ----------------------------

st.markdown("""
<div style='background: linear-gradient(135deg, #001F3F 0%, #003366 100%); color: #FF851B; padding: 30px; border-radius: 20px; text-align: center; margin-bottom: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);'>
    <h1 style='font-size: 2.5em; margin: 0; color: #FFFFFF;'>🎧 Runwith Menu Maker</h1>
    <p style='font-size: 1.3em; margin: 10px 0 0 0; color: #FF851B; font-weight: bold;'>
        音声メニュー作成ツール
    </p>
</div>
""", unsafe_allow_html=True)

# State管理
if 'retake_index' not in st.session_state: st.session_state.retake_index = None
if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# Step 1: お店情報
st.markdown("### 🏪 1. 店舗情報入力")
col1, col2 = st.columns(2)
with col1: 
    store_name = st.text_input("🏠 店名（必須）", placeholder="例：Runwith Cafe")
with col2: 
    menu_title = st.text_input("📖 メニュー名（任意）", placeholder="例：ランチメニュー")

map_url = st.text_input("📍 GoogleマップURL（任意）", placeholder="https://goo.gl/maps/...")
st.caption("※プレイヤーに地図へのアクセスボタンが表示されます。")

st.markdown("---")

# Step 2: メニュー登録
st.markdown("### 📸 2. メニュー素材の登録")
input_method = st.radio("入力方法", ("📂 ファイル選択", "📷 カメラ撮影", "🌐 Web URL"), horizontal=True)

final_image_list = []
target_url = None

if input_method == "📂 ファイル選択":
    uploaded_files = st.file_uploader("メニュー画像", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    if uploaded_files:
        final_image_list.extend(uploaded_files)

elif input_method == "📷 カメラ撮影":
    st.caption("※ブラウザのカメラ許可を「許可」に設定してください。")
    
    # 撮り直しモード
    if st.session_state.retake_index is not None:
        st.warning(f"No.{st.session_state.retake_index + 1} を再撮影中...")
        cam_file = st.camera_input("再撮影", key=f"retake_{st.session_state.camera_key}")
        
        c1, c2 = st.columns(2)
        with c1:
            if cam_file and st.button("決定 (上書き)"):
                st.session_state.captured_images[st.session_state.retake_index] = cam_file
                st.session_state.retake_index = None
                st.session_state.camera_key += 1
                st.rerun()
        with c2:
            if st.button("キャンセル"):
                st.session_state.retake_index = None
                st.rerun()
    else:
        # 通常撮影モード（常に表示）
        cam_file = st.camera_input("メニューを撮影", key=f"cam_{st.session_state.camera_key}")
        
        if cam_file:
            col1, col2 = st.columns(2)
            with col1:
                # 続けて撮影
                if st.button("➕ 追加して次へ", type="primary"):
                    st.session_state.captured_images.append(cam_file)
                    st.session_state.camera_key += 1
                    st.rerun()
            with col2:
                # 撮影終了
                if st.button("✅ 撮影終了 (次へ)"):
                    st.session_state.captured_images.append(cam_file)
                    st.session_state.camera_key += 1
                    st.rerun()
    
    # 撮影済みリストの表示
    if st.session_state.captured_images and st.session_state.retake_index is None:
        if st.button("🗑️ 全て削除"):
            st.session_state.captured_images = []
            st.rerun()
        final_image_list.extend(st.session_state.captured_images)

elif input_method == "🌐 Web URL":
    target_url = st.text_input("読み取りたいURL", placeholder="https://...")

# 画像プレビュー & 削除/再撮影
if final_image_list and st.session_state.retake_index is None:
    st.markdown("#### ▼ 登録画像")
    cols = st.columns(3)
    for i, img in enumerate(final_image_list):
        with cols[i % 3]:
            st.image(img, caption=f"No.{i+1}", use_column_width=True)
            if input_method == "📷 カメラ撮影":
                c1, c2 = st.columns(2)
                if c1.button("再撮影", key=f"rt_{i}"):
                    st.session_state.retake_index = i
                    st.rerun()
                if c2.button("削除", key=f"del_{i}"):
                    st.session_state.captured_images.pop(i)
                    st.rerun()

st.markdown("---")

# Step 3: 生成実行
st.markdown("### 🚀 3. 音声メニュー生成")

can_run = (final_image_list or target_url) and api_key and store_name and st.session_state.retake_index is None

if st.button("🎙️ 作成開始 (Runwith AI)", type="primary", disabled=not can_run, use_container_width=True):
    with st.spinner('Runwith Menu AI が解析中...'):
        output_dir = "menu_audio_temp"
        if os.path.exists(output_dir): shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            
            user_dict_str = json.dumps(user_dict, ensure_ascii=False)
            
            prompt = f"""
            あなたは視覚障害者のためのメニュー読み上げデータ作成のプロです。
            メニューの内容を解析し、聞きやすいように【5つ〜8つ程度の大きなカテゴリー】に分類してまとめてください。
            
            重要ルール:
            1. メニュー項目1つごとに1つのカテゴリーを作らないこと。
            2. 「前菜・サラダ」「メイン料理」「ご飯・麺」「ドリンク」「デザート」のようにグループ化する。
            3. カテゴリー内のメニューは、挨拶などを抜きにして商品名と価格をテンポよく読み上げる文章にする。
            4. 価格の数字には必ず「円」をつけて読み上げる（例：1000 -> 1000円）。
            5. アレルギー、辛さ、量などの重要な注意書きは、省略せず商品名の後に補足して読み上げる。
            
            ★重要：以下の固有名詞・読み方辞書を必ず守ってください。
            {user_dict_str}

            出力フォーマット（JSONのみ）:
            [
              {{"title": "カテゴリー名（例：前菜・サラダ）", "text": "読み上げ文（例：まずは前菜です。シーザーサラダ800円。ポテトサラダ500円。なお、ドレッシングは別添え可能です。）"}},
              {{"title": "カテゴリー名（例：メイン料理）", "text": "読み上げ文（例：続いてメインです。ハンバーグ定食1200円。ステーキ1500円。ご飯の大盛りは無料です。）"}}
            ]
            """
            
            inputs = [prompt]
            if final_image_list:
                for f in final_image_list:
                    f.seek(0)
                    inputs.append({"mime_type": f.type if hasattr(f, 'type') else "image/jpeg", "data": f.getvalue()})
            elif target_url:
                web_text = fetch_text_from_url(target_url)
                inputs.append(web_text[:30000] if web_text else "")

            resp = model.generate_content(inputs)
            
            text_resp = resp.text
            match = re.search(r'\[.*\]', text_resp, re.DOTALL)
            if not match: raise Exception("AIからの応答がJSON形式ではありませんでした。")
            menu_data = json.loads(match.group())

            intro_t = f"こんにちは、{store_name}です。"
            if menu_title: intro_t += f"ただいまより{menu_title}をご紹介します。"
            intro_t += "このプレイヤーは、スクリーンリーダーでの操作に対応しています。"
            intro_t += f"このメニューは、全部で{len(menu_data)}つのカテゴリーに分かれています。まずは目次です。"
            
            for i, tr in enumerate(menu_data): 
                intro_t += f"{i+1}、{tr['title']}。"
                
            intro_t += "それではどうぞ。"
            menu_data.insert(0, {"title": "はじめに・目次", "text": intro_t})

            progress_bar = st.progress(0)
            generated_tracks = asyncio.run(process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar))
            
            html_content = create_standalone_html_player(store_name, generated_tracks, map_url)
            
            date_str = datetime.now().strftime('%Y%m%d')
            safe_name = sanitize_filename(store_name)
            zip_name = f"Runwith_{safe_name}_{date_str}.zip"
            zip_path = os.path.abspath(zip_name)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("index.html", html_content)

            with open(zip_path, "rb") as f:
                zip_data = f.read()

            st.session_state.generated_result = {
                "tracks": generated_tracks,
                "html_content": html_content,
                "html_name": f"{safe_name}_player.html",
                "zip_data": zip_data,
                "zip_name": zip_name,
                "store_name": store_name
            }
            st.success("✨ 完成しました！")
            st.balloons()
            
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

# Step 4: 結果出力 & 店頭POP
if st.session_state.generated_result:
    res = st.session_state.generated_result
    
    st.markdown("---")
    st.markdown("### ▶️ プレビュー")
    render_preview_player(res["tracks"])

    st.markdown("---")
    st.markdown("### 📥 保存")
    
    st.info("""
    **Webプレイヤー**：アクセシビリティ対応済みのHTMLファイルです。スマホへの保存やLINE共有に便利です。  
    **ZIPファイル**：PCでの保存や、My Menu Bookへの追加にご利用ください。
    """)
    
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            f"🌐 Webプレイヤー ({res['html_name']})",
            res['html_content'],
            res['html_name'],
            "text/html",
            type="primary"
        )
    with c2:
        st.download_button(
            f"📦 ZIPファイル ({res['zip_name']})",
            data=res["zip_data"],
            file_name=res['zip_name'],
            mime="application/zip"
        )

    st.markdown("---")
    st.markdown("### 🏪 店頭用POP作成")
    st.warning("⚠️ まずは、ダウンロードしたHTMLファイルをインターネット上に公開（アップロード）してください。")
    
    public_url = st.text_input("公開したURLを入力 (例: https://my-shop.com/menu.html)", key="pop_url")
    
    if public_url:
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={public_url}"
        
        pop_html = f"""
        <div style="border:6px solid #001F3F; padding:30px; background:white; text-align:center; max-width:400px; margin:0 auto; border-radius:20px; color:#001F3F; font-family:sans-serif;">
            <h2 style="color:#001F3F; border-bottom:4px solid #FF851B; display:inline-block; padding-bottom:5px;">🎧 音声メニュー</h2>
            <p style="font-weight:bold; font-size:18px;">スマホでメニューを読み上げます</p>
            <img src="{qr_url}" style="width:200px; border:2px solid #ddd; padding:10px; margin:20px 0;">
            <div style="background:#FFD59E; padding:15px; border-radius:10px; text-align:left; font-size:14px;">
                <strong>使い方：</strong><br>
                1. カメラでQRコードを読み取る<br>
                2. 再生ボタンを押す
            </div>
            <p style="margin-top:15px; font-weight:bold;">{res['store_name']}</p>
        </div>
        """
        components.html(pop_html, height=600, scrolling=True)
