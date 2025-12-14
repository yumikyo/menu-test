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
# HTMLプレイヤー生成（JS埋め込み完全版・シークバー機能付き）
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

/* 再生中タイトルエリア */
.box { 
    background: var(--bg-dark); 
    border: 5px solid var(--text-orange); 
    border-radius: 15px; 
    padding: 25px; 
    text-align: center; 
    margin-bottom: 15px; 
    min-height: 100px; 
    display: flex; 
    align-items: center; 
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 10px rgba(0,0,0,0.3);
    transition: transform 0.1s;
    user-select: none;
}
.box:active { transform: scale(0.98); }
.box:hover { background-color: #004080; }

.ti { font-size: 1.8em; font-weight: bold; color: var(--text-orange); }
.ctrl-group { display: flex; flex-direction: column; gap: 20px; margin-bottom: 25px; }
.main-ctrl { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
button { width: 100%; padding: 25px 0; font-size: 1.8em; font-weight: bold; color: var(--bg-navy) !important; background: var(--text-orange) !important; border: 3px solid var(--accent-white); border-radius: 15px; cursor: pointer; min-height: 80px; }
button.reset-btn { font-size: 1.3em; background: var(--bg-dark) !important; color: var(--accent-white) !important; border-color: var(--text-orange); }
.map-btn { display: block; width: 100%; padding: 25px; background-color: var(--accent-white); color: var(--bg-navy) !important; text-decoration: none; border-radius: 15px; font-size: 1.6em; font-weight: bold; border: 3px solid var(--text-orange); box-sizing: border-box; text-align: center; }

/* シークバーのデザイン */
.seek-container {
    background: #001021;
    padding: 15px 20px;
    border-radius: 12px;
    margin-bottom: 25px;
    border: 1px solid #FF851B;
}
input[type=range] {
    -webkit-appearance: none;
    width: 100%;
    background: transparent;
    height: 40px; /* 操作しやすい高さ */
    cursor: pointer;
}
input[type=range]:focus { outline: none; }
input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none;
    height: 36px;
    width: 36px;
    border-radius: 50%;
    background: #FF851B;
    border: 4px solid #FFFFFF;
    margin-top: -14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.5);
}
input[type=range]::-webkit-slider-runnable-track {
    width: 100%;
    height: 12px;
    cursor: pointer;
    background: #555;
    border-radius: 6px;
    border: 1px solid #888;
}
.time-disp {
    display: flex;
    justify-content: space-between;
    font-size: 1.2em;
    font-weight: bold;
    color: #FFFFFF;
    margin-top: 5px;
}

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
            <div class="ti" id="ti" aria-live="polite">▶ 読み込み中...</div>
        </div>

        <div class="seek-container">
            <input type="range" id="sb" value="0" min="0" step="1" aria-label="再生位置">
            <div class="time-disp">
                <span id="ct">0:00</span>
                <span id="dt">0:00</span>
            </div>
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
const sb=document.getElementById('sb'); const ct=document.getElementById('ct'); const dt=document.getElementById('dt');

function init(){ ren(); ld(0); csp(); updateTitleUI(); }

function ld(i){ idx=i; au.src=pl[idx].src; updateTitleUI(); ren(); csp(); }

function updateTitleUI() {
    const icon = au.paused ? "▶" : "⏸";
    ti.innerText = icon + " " + pl[idx].title;
}

function fmt(s) {
    const m = Math.floor(s / 60);
    const ss = Math.floor(s % 60);
    return m + ":" + (ss < 10 ? "0" : "") + ss;
}

// 音声メタデータ読み込み完了時
au.onloadedmetadata = function() {
    sb.max = au.duration;
    dt.innerText = fmt(au.duration);
    ct.innerText = fmt(0);
};

// 再生位置が変わった時
au.ontimeupdate = function() {
    sb.value = au.currentTime;
    ct.innerText = fmt(au.currentTime);
};

// シークバー操作時
sb.oninput = function() {
    au.currentTime = sb.value;
    ct.innerText = fmt(sb.value);
};

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
# プレビュー用プレイヤー（簡易版・シークバーなし）
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
    const pl=__PLAYLIST__;let x=0;const au=document.getElementById('
