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

# CSSでボタンのスタイル調整（高齢者視認性向上）
st.markdown("""
<style>
    div[data-testid="column"] { margin-bottom: 10px; }
    .stButton>button { 
        font-weight: bold; 
        font-size: 16px;
        min-height: 50px;
    }
    .stRadio > div > div > label { font-size: 16px; font-weight: bold; }
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
    except: 
        return None

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
        
        # チャプター番号をシンプルに読み上げる（i=0ははじめになので番号なし）
        if i > 0: 
             speech_text = f"{i}番、{track['title']}。\n{track['text']}"
             
        tasks.append(generate_single_track_fast(speech_text, save_path, voice_code, rate_value))
        track_info_list.append({"title": track['title'], "path": save_path})
    
    total = len(tasks)
    completed = 0
    for task in asyncio.as_completed(tasks):
        await task
        completed += 1
        progress_bar.progress(completed / total)
    return track_info_list

# ★Runwithブランドカラー（紺×オレンジ）対応・アクセシビリティ完全版 HTMLプレイヤー★
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
/* Runwithブランドカラー（高齢者・視覚障害者対応） */
:root {
    --bg-navy: #001F3F;      /* 濃紺：コントラスト最高 */
    --text-orange: #FF851B;  /* 明るいオレンジ：視認性最高 */
    --accent-white: #FFFFFF; /* 白：最高コントラスト */
    --bg-dark: #003366;      /* ダークアクセント */
}

body {
    font-family: "Helvetica Neue", "Hiragino Kaku Gothic ProN", "メイリオ", Meiryo, sans-serif;
    background: var(--bg-navy);
    color: var(--text-orange);
    margin: 0;
    padding: 15px;
    line-height: 1.8;
    font-size: 18px; /* 高齢者視認性向上 */
}

.c { max-width: 600px; margin: 0 auto; }

h1 {
    text-align: center;
    font-size: 2em;
    color: var(--accent-white);
    border-bottom: 4px solid var(--text-orange);
    padding-bottom: 15px;
    margin-bottom: 25px;
}
h2 {
    font-size: 1.5em;
    color: var(--accent-white); 
    margin-top: 35px;
    border-left: 10px solid var(--text-orange);
    padding-left: 15px;
    padding-bottom: 8px;
}

.box {
    background: var(--bg-dark);
    border: 5px solid var(--text-orange);
    border-radius: 15px;
    padding: 25px;
    text-align: center;
    margin-bottom: 25px;
    min-height: 90px;
    display: flex; 
    align-items: center; 
    justify-content: center;
}
.ti { 
    font-size: 1.8em; 
    font-weight: bold; 
    color: var(--text-orange); 
}

/* 操作パネル：視覚障害者・高齢者最適化 */
.ctrl-group {
    display: flex; 
    flex-direction: column; 
    gap: 20px; 
    margin-bottom: 25px;
}
.main-ctrl { 
    display: grid; 
    grid-template-columns: 1fr 1fr; 
    gap: 20px; 
}

button {
    width: 100%;
    padding: 25px 0;
    font-size: 1.8em; 
    font-weight: bold;
    color: var(--bg-navy) !important;
    background: var(--text-orange) !important;
    border: 3px solid var(--accent-white);
    border-radius: 15px; 
    cursor: pointer;
    touch-action: manipulation;
    min-height: 80px;
    transition: all 0.2s;
}
button.play-btn { 
    font-size: 2.2em; 
    background: var(--text-orange) !important; 
    color: var(--bg-navy) !important; 
}
button.reset-btn { 
    font-size: 1.3em; 
    background: var(--bg-dark) !important; 
    color: var(--accent-white) !important; 
    border-color: var(--text-orange); 
}

button:hover { opacity: 0.9; transform: translateY(1px); }
button:active { transform: translateY(3px); }
button:focus { 
    outline: 5px solid var(--accent-white); 
    outline-offset: 3px; 
    box-shadow: 0 0 0 4px rgba(255,133,27,0.3);
}

.map-btn {
    display: block; 
    width: 100%; 
    padding: 25px; 
    background-color: var(--accent-white); 
    color: var(--bg-navy) !important; 
    text-decoration: none; 
    border-radius: 15px; 
    font-size: 1.6em; 
    font-weight: bold;
    border: 3px solid var(--text-orange); 
    box-sizing: border-box; 
    text-align: center;
    transition: all 0.2s;
}
.map-btn:hover { background-color: #f0f0f0; transform: translateY(1px); }
.map-btn:focus { outline: 5px solid var(--text-orange); outline-offset: 3px; }

.lst { 
    border-top: 4px solid var(--text-orange); 
    padding-top: 20px; 
    margin-top: 25px; 
}
.itm {
    padding: 25px 15px; 
    border-bottom: 2px solid #666; 
    cursor: pointer; 
    font-size: 1.4em; 
    color: var(--accent-white);
    border-radius: 10px;
    margin-bottom: 8px;
    transition: all 0.2s;
}
.itm:hover { background: var(--bg-dark); }
.itm.active {
    background: var(--text-orange) !important; 
    color: var(--bg-navy) !important; 
    font-weight: bold; 
    border-left: 12px solid var(--accent-white);
    box-shadow: 0 4px 12px rgba(255,133,27,0.4);
}
.itm:focus {
    outline: 4px solid var(--accent-white);
    outline-offset: 2px;
    background: var(--bg-dark);
}
</style>
</head>
<body>
<main class="c" role="main" aria-label="音声メニュー再生アプリ">
    <h1>🎧 __STORE_NAME__</h1>
    __MAP_BUTTON__
    
    <section aria-label="再生状況表示">
        <div class="box">
            <div class="ti" id="ti" aria-live="polite" role="status">準備中...</div>
        </div>
    </section>

    <!-- 視覚障害者向け：非表示のオーディオ要素 -->
    <audio id="au" 
           preload="metadata"
           style="width:1px;height:1px;opacity:0;position:absolute;"
           aria-label="メニュー読み上げプレイヤー">
    </audio>

    <section aria-label="操作パネル" class="ctrl-group">
        <button onclick="restart()" 
                class="reset-btn" 
                aria-label="最初から再生する">
            ⏮ 最初に戻る
        </button>
        <button onclick="toggle()" 
                id="pb" 
                class="play-btn" 
                role="button" 
                aria-pressed="false"
                aria-label="再生・一時停止">
            ▶ 再生
        </button>
        <div class="main-ctrl">
            <button onclick="prev()" 
                    aria-label="前のチャプター">
                ⏮ 前
            </button>
            <button onclick="next()" 
                    aria-label="次のチャプター">
                次 ⏭
            </button>
        </div>
    </section>

    <div style="text-align:center; margin:25px 0; padding:20px; background:var(--bg-dark); border-radius:12px;">
        <label for="sp" style="font-size:1.4em; color:var(--accent-white); font-weight:bold;">話す速さ: </label>
        <select id="sp" 
                onchange="csp()" 
                style="font-size:1.4em; padding:12px; border-radius:10px; border:2px solid var(--text-orange); background:var(--accent-white); color:var(--bg-navy);">
            <option value="0.8">0.8 (ゆっくり)</option>
            <option value="1.0" selected>1.0 (標準)</option>
            <option value="1.2">1.2 (せっかち)</option>
            <option value="1.5">1.5 (爆速)</option>
        </select>
    </div>

    <section aria-label="チャプター一覧">
        <h2>📜 メニュー一覧</h2>
        <div id="ls" class="lst" role="list" aria-label="メニューのチャプター一覧"></div>
    </section>
</main>

<script>
const pl=__PLAYLIST_JSON__;let idx=0;
const au=document.getElementById('au');
const ti=document.getElementById('ti');
const pb=document.getElementById('pb');

function init(){
    ren();
    ld(0);
    csp();
    // ページ読み込み時に音声ガイド
    speakIntro();
}

function speakIntro(){
    const msg = new SpeechSynthesisUtterance("音声メニューが準備できました。再生ボタンで開始してください。");
    msg.lang = 'ja-JP';
    msg.rate = 0.9;
    speechSynthesis.speak(msg);
}

function ld(i){
    idx=i;
    au.src=pl[idx].src;
    ti.innerText=pl[idx].title;
    ren();
    csp();
    // ステータス更新
    updateAriaStatus();
}

function toggle(){
    if(au.paused){
        au.play();
        pb.innerText="⏸ 一時停止";
        pb.setAttribute("aria-pressed", "true");
        pb.setAttribute("aria-label", "一時停止");
    }else{
        au.pause();
        pb.innerText="▶ 再生";
        pb.setAttribute("aria-pressed", "false");
        pb.setAttribute("aria-label", "再生");
    }
}

function restart(){
    idx=0;
    ld(0);
    au.play();
    pb.innerText="⏸ 一時停止";
    pb.setAttribute("aria-pressed", "true");
}

function next(){
    if(idx<pl.length-1){ 
        ld(idx+1); 
        au.play(); 
        pb.innerText="⏸ 一時停止";
        pb.setAttribute("aria-pressed", "true");
    }
}

function prev(){
    if(idx>0){ 
        ld(idx-1); 
        au.play(); 
        pb.innerText="⏸ 一時停止";
        pb.setAttribute("aria-pressed", "true");
    }
}

function csp(){
    au.playbackRate=parseFloat(document.getElementById('sp').value);
}

au.onended=function(){
    if(idx<pl.length-1){ 
        next(); 
    } else { 
        pb.innerText="▶ 再生";
        pb.setAttribute("aria-pressed", "false");
        idx=0; 
        ld(0); 
        au.pause(); 
    }
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
        
        m.setAttribute("aria-label", label);
        m.innerText=label;
        m.onclick=()=>{
            ld(i);
            au.play();
            pb.innerText="⏸ 一時停止";
            pb.setAttribute("aria-pressed", "true");
        };
        // ★キーボード操作修正版★
        m.onkeydown=(e)=>{
            if(e.key==='Enter' || e.key===' '){
                e.preventDefault();
                m.click(); // m.click()で正しく動作
            }
        };
        d.appendChild(m);
    });
}

function updateAriaStatus(){
    ti.setAttribute("aria-label", `現在再生中: ${pl[idx].title}`);
}

// キーボードナビゲーション強化
document.addEventListener('keydown', function(e) {
    if(e.target.closest('button, [role="button"], [tabindex="0"]')) return;
    
    switch(e.key) {
        case 'ArrowRight': e.preventDefault(); next(); break;
        case 'ArrowLeft': e.preventDefault(); prev(); break;
        case ' ': case 'Enter': 
            e.preventDefault(); 
            document.querySelector('.play-btn').click(); 
            break;
        case 'Home': e.preventDefault(); restart(); break;
    }
});

init();
</script>
</body>
</html>"""

    final_html = html_template.replace("__STORE_NAME__", store_name)
    final_html = html_template.replace("__PLAYLIST_JSON__", playlist_json_str)
    final_html = html_template.replace("__MAP_BUTTON__", map_button_html)
    return final_html

# プレビュー用プレイヤー（Runwithカラー対応）
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
    .p-box{
        border:4px solid #001F3F;
        border-radius:15px;
        padding:20px;
        background:#fff;
        text-align:center;
        box-shadow:0 5px 20px rgba(0,0,0,0.1);
    }
    .t-ti{
        font-size:20px;
        font-weight:bold;
        color:#001F3F;
        margin-bottom:15px;
        padding:15px;
        background:#FF851B;
        color:#001F3F !important;
        border-radius:10px;
        border-left:6px solid #fff;
    }
    .ctrls{
        display:flex; 
        gap:15px; 
        margin:20px 0;
        flex-wrap:wrap;
    }
    button {
        flex: 1;
        background-color: #FF851B !important; 
        color: #001F3F !important; 
        border: 2px solid #001F3F !important;
        border-radius: 12px; 
        font-size: 22px; 
        padding: 15px 0;
        cursor: pointer; 
        min-height: 60px;
        font-weight: bold;
    }
    button:hover { background-color: #FF6B00 !important; }
    button:focus { 
        outline: 4px solid #001F3F !important; 
        outline-offset: 2px; 
    }
    .lst{
        text-align:left;
        max-height:180px;
        overflow-y:auto;
        border-top:3px solid #001F3F;
        margin-top:15px;
        padding-top:10px;
    }
    .it{
        padding:12px;
        border-bottom:2px solid #eee;
        cursor:pointer;
        font-size:16px;
        border-radius:8px;
        margin-bottom:5px;
    }
    .it:focus{
        outline:3px solid #001F3F; 
        background:#f0f8ff;
    }
    .it.active{
        color:#FF851B !important;
        font-weight:bold;
        background:#001F3F !important;
        border-left:6px solid #FF851B;
    }
    </style></head><body>
    <div class="p-box">
        <div id="ti" class="t-ti">...</div>
        <audio id="au" controls style="width:100%;height:40px;margin:15px 0;"></audio>
        <div class="ctrls">
            <button onclick="pv()" aria-label="前へ">⏮</button>
            <button onclick="tg()" id="pb" aria-label="再生">▶</button>
            <button onclick="nx()" aria-label="次へ">⏭</button>
        </div>
        <div style="font-size:14px;color:#666; margin-top:10px;">
            速度:<select id="sp" onchange="sp()">
                <option value="0.8">0.8</option>
                <option value="1.0" selected>1.0</option>
                <option value="1.2">1.2</option>
                <option value="1.5">1.5</option>
            </select>
        </div>
        <div id="ls" class="lst" role="list"></div>
    </div>
    <script>
    const pl=__PLAYLIST__;let x=0;
    const au=document.getElementById('au');
    const ti=document.getElementById('ti');
    const pb=document.getElementById('pb');
    const ls=document.getElementById('ls');
    function init(){rn();ld(0);sp();}
    function ld(i){
        x=i;au.src=pl[x].src;ti.innerText=pl[x].title;rn();sp();
    }
    function tg(){
        if(au.paused){
            au.play();
            pb.innerText="⏸";
            pb.setAttribute("aria-label","一時停止");
            pb.setAttribute("aria-pressed","true");
        }else{
            au.pause();
            pb.innerText="▶";
            pb.setAttribute("aria-label","再生");
            pb.setAttribute("aria-pressed","false");
        }
    }
    function nx(){
        if(x<pl.length-1){
            ld(x+1);au.play();
            pb.innerText="⏸";
            pb.setAttribute("aria-label","一時停止");
            pb.setAttribute("aria-pressed","true");
        }
    }
    function pv(){
        if(x>0){
            ld(x-1);au.play();
            pb.innerText="⏸";
            pb.setAttribute("aria-label","一時停止");
            pb.setAttribute("aria-pressed","true");
        }
    }
    function sp(){
        au.playbackRate=parseFloat(document.getElementById('sp').value);
    }
    au.onended=function(){
        if(x<pl.length-1){
            nx();
        }else{
            pb.innerText="▶";
            pb.setAttribute("aria-label","再生");
            pb.setAttribute("aria-pressed","false");
        }
    };
    function rn(){
        ls.innerHTML="";
        pl.forEach((t,i)=>{
            const d=document.createElement('div');
            d.className="it "+(i===x?"active":"");
            let l=t.title; 
            if(i>0){l=i+". "+t.title;}
            d.innerText=l;
            d.setAttribute("role","listitem");
            d.setAttribute("tabindex","0");
            d.onclick=()=>{
                ld(i);au.play();
                pb.innerText="⏸";
                pb.setAttribute("aria-label","一時停止");
                pb.setAttribute("aria-pressed","true");
            };
            // ★修正済み：キーボード操作★
            d.onkeydown=(e)=>{
                if(e.key==='Enter' || e.key===' '){
                    e.preventDefault();
                    d.click();
                }
            };
            ls.appendChild(d);
        });
    }
    init();
    </script></body></html>"""
    
    final_html = html_template.replace("__PLAYLIST__", playlist_json)
    components.html(final_html, height=500)

# --- メインUI（Runwithブランド） ---
with st.sidebar:
    st.markdown("""
    <div style='background:#001F3F;color:#FF851B;padding:20px;border-radius:15px;text-align:center;font-weight:bold;font-size:18px;'>
        🎯 Runwith設定
    </div>
    """, unsafe_allow_html=True)
    
    st.header("🔧 基本設定")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ APIキー認証済み")
        st.balloons()
    else:
        api_key = st.text_input("🔑 Gemini APIキー", type="password", help="Google AI Studioから取得")
    
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
            st.error(f"APIキーエラー: {e}")
    
    st.divider()
    st.header("🗣️ 音声設定")
    voice_options = {"👩 女性": "ja-JP-NanamiNeural", "👨 男性": "ja-JP-KeitaNeural"}
    selected_voice = st.radio("声の種類", list(voice_options.keys()), horizontal=True)
    voice_code = voice_options[selected_voice]
    rate_value = "+10%"

    st.divider()
    st.header("📝 読み上げモード")
    reading_mode = st.radio("内容の詳しさ", 
                           ("💬 商品名と価格のみ (シンプル)", "🌟 説明・解説付き (詳細)"), 
                           index=1, horizontal=True)

    # 辞書機能
    st.divider()
    st.header("📖 カスタム辞書")
    st.caption("店独自の読み方を登録（例：店名・固有名詞）")
    user_dict = load_dictionary()
    
    with st.form("dict_form", clear_on_submit=True):
        col1, col2 = st.columns([3,1])
        new_word = col1.text_input("単語", placeholder="例: タナカ丼")
        new_read = col1.text_input("読み", placeholder="例: たなかどん")
        if col2.form_submit_button("➕ 追加", use_container_width=True):
            if new_word and new_read:
                user_dict[new_word] = new_read
                save_dictionary(user_dict)
                st.success(f"✅ 「{new_word}」を登録完了！")
                st.rerun()

    if user_dict:
        with st.expander(f"📚 登録済み ({len(user_dict)}語)"):
            for word, read in list(user_dict.items()):
                col1, col2 = st.columns([3,1])
                col1.markdown(f"**{word}** → `{read}`")
                if col2.button("🗑️", key=f"del_{hash(word)}", use_container_width=True):
                    del user_dict[word]
                    save_dictionary(user_dict)
                    st.rerun()

# メインページ
st.markdown("""
<div style='
    background: linear-gradient(135deg, #001F3F 0%, #003366 100%);
    color: #FF851B;
    padding: 30px;
    border-radius: 20px;
    text-align: center;
    margin-bottom: 30px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
'>
    <h1 style='font-size: 2.5em; margin: 0; color: #FFFFFF;'>🎧 Runwith Menu AI</h1>
    <p style='font-size: 1.3em; margin: 10px 0 0 0; color: #FF851B; font-weight: bold;'>
        視覚障害者・高齢者対応 音声メニュー自動生成
    </p>
</div>
""", unsafe_allow_html=True)

st.caption("Powered by Runwith AI - 飲食店のバリアフリーを伴走支援")

# State管理
if 'retake_index' not in st.session_state: st.session_state.retake_index = None
if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# Step 1: お店情報
st.markdown("### 🏪 1. お店情報の入力")
col1, col2 = st.columns(2)
with col1: 
    store_name = st.text_input("🏠 店舗名（必須）", 
                              placeholder="例：カフェタナカ", 
                              help="音声ガイドで読み上げられる店名")
with col2: 
    menu_title = st.text_input("📖 メニュータイトル（任意）", 
                              placeholder="例：冬季限定ランチ", 
                              help="「ただいまより冬季限定ランチを…」")

map_url = st.text_input("📍 GoogleマップURL（任意）", 
                       placeholder="https://maps.app.goo.gl/xxx",
                       help="店頭POPに地図リンクボタンが追加されます")

st.markdown("---")

# Step 2: メニュー登録
st.markdown("### 📸 2. メニューの登録方法")
input_method = st.radio("入力方法", 
                       ("📂 アルバムから選択", "📷 その場で撮影", "🌐 ホームページURL"), 
                       horizontal=True)

final_image_list = []
target_url = None

if input_method == "📂 アルバムから選択":
    uploaded_files = st.file_uploader("メニュー写真を選択", 
                                     type=['png', 'jpg', 'jpeg'], 
                                     accept_multiple_files=True,
                                     help="複数枚アップロードで全メニュー解析")
    if uploaded_files: 
        final_image_list.extend(uploaded_files)

elif input_method == "📷 その場で撮影":
    if st.session_state.retake_index is not None:
        target_idx = st.session_state.retake_index
        st.warning(f"🔄 No.{target_idx + 1} を再撮影中...")
        retake_camera_key = f"retake_{target_idx}_{st.session_state.camera_key}"
        camera_file = st.camera_input("📷 再撮影", key=retake_camera_key)
        
        col1, col2 = st.columns(2)
        with col1:
            if camera_file and st.button("✅ 決定", type="primary", use_container_width=True):
                st.session_state.captured_images[target_idx] = camera_file
                st.session_state.retake_index = None
                st.session_state.camera_key += 1
                st.rerun()
        with col2:
            if st.button("❌ キャンセル", use_container_width=True):
                st.session_state.retake_index = None
                st.rerun()
    else:
        if st.button("📷 カメラ起動", type="primary", use_container_width=True):
            st.session_state.show_camera = True
            st.rerun()
        
        if st.session_state.show_camera:
            camera_file = st.camera_input("撮影する（複数可）", key=f"cam_{st.session_state.camera_key}")
            if camera_file:
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("➕ 次も撮影", type="primary", use_container_width=True):
                        st.session_state.captured_images.append(camera_file)
                        st.session_state.camera_key += 1
                        st.rerun()
                with col_btn2:
                    if st.button("✅ 撮影終了", type="primary", use_container_width=True):
                        st.session_state.captured_images.append(camera_file)
                        st.session_state.show_camera = False
                        st.rerun()
            else:
                if st.button("❌ 撮影中止", use_container_width=True):
                    st.session_state.show_camera = False
                    st.rerun()
    
    if st.session_state.captured_images and st.session_state.retake_index is None:
        if st.button("🗑️ 全削除", type="secondary"):
            st.session_state.captured_images = []
            st.rerun()
        final_image_list.extend(st.session_state.captured_images)

elif input_method == "🌐 ホームページURL":
    target_url = st.text_input("メニューURL", placeholder="https://example.com/menu")

# 画像プレビュー
if final_image_list and st.session_state.retake_index is None:
    st.markdown("### 👀 撮影確認")
    cols_per_row = 3
    for i in range(0, len(final_image_list), cols_per_row):
        cols = st.columns(cols_per_row)
        batch = final_image_list[i:i+cols_per_row]
        for j, img_file in enumerate(batch):
            global_idx = i + j
            with cols[j]:
                st.image(img_file, caption=f"No.{global_idx+1}", use_container_width=True)
                if input_method == "📷 その場で撮影":
                    col_rt, col_del = st.columns(2)
                    with col_rt:
                        if st.button("🔄 撮り直し", key=f"rt_{global_idx}"):
                            st.session_state.retake_index = global_idx
                            st.rerun()
                    with col_del:
                        if st.button("🗑️ 削除", key=f"del_{global_idx}"):
                            st.session_state.captured_images.pop(global_idx)
                            st.rerun()

st.markdown("---")

# Step 3: 生成
st.markdown("### 🚀 3. Runwith AIで音声メニュー作成")
disable_create = st.session_state.retake_index is not None or not final_image_list and not target_url

if st.button("🎙️ AI解析＆音声生成開始", 
             type="primary", 
             use_container_width=True, 
             disabled=disable_create,
             help="画像/URL → AI解析 → 音声生成 → 完成！"):
    
    if not (api_key and target_model_name and store_name):
        st.error("❌ 設定・店舗名を確認してください")
        st.stop()
    if not (final_image_list or target_url):
        st.warning("⚠️ メニュー画像またはURLを入力してください")
        st.stop()

    with st.spinner('🎯 Runwith AI がメニューを解析中...'):
        output_dir = os.path.abspath("menu_audio_album")
        if os.path.exists(output_dir): 
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            parts = []
            
            # ユーザー辞書
            user_dict_str = json.dumps(user_dict, ensure_ascii=False)
            
            # 読み上げモード別指示
            mode_instruction = ""
            if "シンプル" in reading_mode:
                mode_instruction = """
                - 商品名＋価格のみ。説明文一切不要
                - 「美味しそう」「おすすめ」など形容詞禁止
                - 淡々と情報伝達のみ
                """
            else:
                mode_instruction = """
                - 写真の特徴（「赤くて辛そう」「ボリューム満点」など）を一言添える
                - 料理の魅力を伝えて食欲を刺激
                - 視覚障害者が「食べたい！」と思える表現
                """

            prompt = f"""あなたは視覚障害者の外食パートナー「Runwith Menu AI」です。

【ミッション】
メニュー画像を解析し、5〜8つの論理的チャプターに整理。料理選びを支援。

【厳格ルール】
1. カテゴリ分け必須：「前菜」「メイン」「ドリンク」など
2. 価格は必ず「○○円」と明記
3. アレルギー・辛さ情報は絶対省略禁止
4. {mode_instruction}

【固有名詞辞書（厳守）】
{user_dict_str}

【出力形式（JSONのみ）】
[
  {{"title": "カテゴリー名", "text": "読み上げ原稿"}},
  {{"title": "カテゴリー名", "text": "読み上げ原稿"}}
]
"""
            
            if final_image_list:
                parts.append(prompt)
                for f in final_image_list:
                    f.seek(0)
                    parts.append({
                        "mime_type": f.type if hasattr(f, 'type') else 'image/jpeg', 
                        "data": f.getvalue()
                    })
            elif target_url:
                web_text = fetch_text_from_url(target_url)
                if not web_text: 
                    st.error("❌ URLからテキスト取得失敗")
                    st.stop()
                parts.append(prompt + f"\n\n[Webテキスト]\n{web_text[:30000]}")

            # AI生成
            resp = None
            for attempt in range(3):
                try: 
                    resp = model.generate_content(parts)
                    break
                except exceptions.ResourceExhausted: 
                    time.sleep(5)
                except: 
                    pass

            if not resp: 
                st.error("❌ AI生成に失敗しました")
                st.stop()

            # JSON抽出
            text_resp = resp.text
            start = text_resp.find('[')
            end = text_resp.rfind(']') + 1
            if start == -1: 
                st.error("❌ JSON形式の解析結果が取得できませんでした")
                st.stop()
            
            menu_data = json.loads(text_resp[start:end])

            # 導入トラック自動生成
            intro_text = f"こんにちは、{store_name}へようこそ。Runwith Menu AIがお手伝いします。"
            if menu_title: 
                intro_text += f" ただいま{menu_title}をご案内します。"
            intro_text += f" スクリーンリーダー対応の音声メニューです。全{len(menu_data)}チャプターあります。目次です。"
            for i, track in enumerate(menu_data):
                intro_text += f" {i+1}、{track['title']}。"
            intro_text += " それではごゆっくりお選びください。"
            
            menu_data.insert(0, {"title": "🎉 はじめに・目次", "text": intro_text})

            # 音声生成
            progress_bar = st.progress(0)
            st.info("🔊 高品質音声生成中...（並列処理）")
            generated_tracks = asyncio.run(
                process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar)
            )

            # HTML＋ZIPパッケージ作成
            html_content = create_standalone_html_player(store_name, generated_tracks, map_url)
            
            date_str = datetime.now().strftime('%Y%m%d_%H%M')
            safe_name = sanitize_filename(store_name)
            zip_name = f"Runwith_{safe_name}_{date_str}.zip"
            zip_path = os.path.abspath(zip_name)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(output_dir):
                    for file in files: 
                        zf.write(os.path.join(root, file), file)

            with open(zip_path, "rb") as f:
                zip_data = f.read()

            st.session_state.generated_result = {
                "zip_data": zip_data,
                "zip_name": zip_name,
                "html_content": html_content, 
                "html_name": f"Runwith_{safe_name}_{date_str}.html",
                "tracks": generated_tracks,
                "store_name": store_name
            }
            st.success("🎉 音声メニュー完成！")
            st.balloons()

        except Exception as e: 
            st.error(f"❌ 生成エラー: {str(e)}")
            st.stop()

# 結果表示
if st.session_state.get('generated_result'):
    result = st.session_state.generated_result
    st.markdown("---")
    
    st.markdown("### 🎵 プレビュー再生")
    render_preview_player(result["tracks"])
    
    st.markdown("---")
    st.markdown("### 💾 完成パッケージダウンロード")
    
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label=f"🌐 Webプレイヤー ({result['html_name']})",
            data=result['html_content'], 
            file_name=result['html_name'],
            mime="text/html",
            type="primary",
            help="スマホで開ける完成版。LINE共有OK"
        )
    with col2:
        st.download_button(
            label=f"📦 音声ZIP ({result['zip_name']})", 
            data=result["zip_data"], 
            file_name=result['zip_name'], 
            mime="application/zip",
            help="全音声ファイル一括保存"
        )

    # QRコードPOP生成
    st.markdown("---")
    st.markdown("### 🏪 店頭用QRコード・POP")
    st.info("💡 生成した「Webプレイヤー」を自社サイトにアップロードし、URLを入力すると店頭POPが自動作成されます")
    
    public_url = st.text_input("📡 公開URLを入力", 
                              placeholder="https://your-site.com/menu_player.html",
                              help="HTMLファイルを公開したURL")
    
    if public_url:
        qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={public_url}"
        
        pop_html = f"""
        <div style="
            border: 6px solid #001F3F; 
            padding: 40px; 
            background: linear-gradient(135deg, #FFFFFF 0%, #F8F9FA 100%); 
            text-align: center; 
            max-width: 450px; 
            margin: 20px auto; 
            font-family: 'Hiragino Kaku Gothic Pro', 'メイリオ', sans-serif;
            box-shadow: 0 15px 40px rgba(0,0,0,0.2);
            border-radius: 20px;
            color: #001F3F;
        ">
            <h2 style="
                background: linear-gradient(90deg, #001F3F, #FF851B);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 28px; 
                margin: 0 0 20px 0; 
                font-weight: bold;
            ">
                🎧 音声メニュー
            </h2>
            <p style="font-size: 18px; font-weight: bold; margin: 25px 0; color: #001F3F;">
                📱 スマホで読み上げメニュー<br>誰でも簡単に使えます
            </p>
            
            <div style="background:#FF851B;padding:15px;border-radius:15px;margin:20px 0;">
                <img src="{qr_api_url}" 
                     alt="音声メニューQRコード" 
                     style="width: 220px; height: 220px; margin: 0 auto; border: 4px solid #001F3F; border-radius: 15px; padding:10px; box-shadow: 0 5px 15px rgba(0,0,0,0.2);">
            </div>
            
            <div style="background:#E8F4FD;padding:20px;border-radius:15px;margin:20px 0;font-size:16px;color:#001F3F;">
                <strong>👆 使い方：</strong><br>
                ① QRコードを読み取る<br>
                ② 画面が開いたら▶再生ボタン<br>
                ③ メニュー一覧から選んでください
            </div>
            
            <div style="
                margin-top: 25px; 
                padding: 15px;
                background: #FFD59E;
                border-radius: 12px;
                border-left: 6px solid #FF851B;
                font-size: 16px;
            ">
                <strong>💁‍♂️ 店員さんへ：</strong><br>
                視覚障害のお客様がいらしたら、<br>
                スマホでこのQRを読み取っていただき、<br>
                再生ボタンを押してください。
            </div>
            
            <div style="
                margin-top: 25px; 
                font-weight: bold; 
                font-size: 22px; 
                color: #001F3F;
                background: linear-gradient(90deg, #001F3F, #FF851B);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            ">
                {result['store_name']}
            </div>
        </div>
        """
        
        st.markdown("### 🎨 店頭POPプレビュー")
        st.caption("*この画面を印刷またはスクショで店頭に設置*")
        components.html(pop_html, height=750)
        
        st.download_button(
            label="🖨️ POPを画像保存",
            data=pop_html,
            file_name=f"{result['store_name']}_音声メニューPOP.html",
            mime="text/html"
        )

st.markdown("---")
st.markdown("""
<div style='
    background: #001F3F; 
    color: #FF851B; 
    padding: 20px; 
    border-radius: 15px; 
    text-align: center; 
    font-size: 14px;
'>
    ✨ Runwith Menu AI - 飲食店のバリアフリーを伴走支援<br>
    視覚障害者・高齢者対応音声メニューをワンクリックで作成
</div>
""", unsafe_allow_html=True)
