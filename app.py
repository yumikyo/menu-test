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

# 非同期処理の適用
nest_asyncio.apply()

# ページ設定
st.set_page_config(page_title="Multilingual Menu Generator", layout="wide")

# --- 定数・辞書設定 ---

# 言語設定とUIテキスト
LANG_SETTINGS = {
    "Japanese": {
        "code": "ja",
        "voice_gender": ["女性 (七海)", "男性 (慶太)"],
        "voice_ids": ["ja-JP-NanamiNeural", "ja-JP-KeitaNeural"],
        "ui": {
            "title": "カテゴリー", "text": "説明", 
            "loading": "読み込み中...", "speed": "速度", 
            "map_btn": "📍 地図・アクセス (Google Map)",
            "intro": "こんにちは。こちらがメニューのご案内です。",
            "toc": "目次です。",
            "outro": "ごゆっくりお選びください。"
        }
    },
    "English (UK)": {  # UKに変更
        "code": "en",
        "voice_gender": ["Female (Sonia - UK)", "Male (Ryan - UK)"], # UK音声に変更
        "voice_ids": ["en-GB-SoniaNeural", "en-GB-RyanNeural"],      # EdgeTTSのUK ID
        "ui": {
            "title": "Category", "text": "Description",
            "loading": "Loading...", "speed": "Speed",
            "map_btn": "📍 Open Map (Google Map)",
            "intro": "Hello. Here is the menu introduction.",
            "toc": "Here is the table of contents.",
            "outro": "Please take your time to choose."
        }
    },
    "Chinese": {
        "code": "zh",
        "voice_gender": ["女性 (晓晓)", "男性 (云希)"],
        "voice_ids": ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"],
        "ui": {
            "title": "类别", "text": "描述",
            "loading": "加载中...", "speed": "速度",
            "map_btn": "📍 打开地图 (Google Map)",
            "intro": "你好。这里是菜单介绍。",
            "toc": "这是目录。",
            "outro": "请慢慢挑选。"
        }
    },
    "Korean": {
        "code": "ko",
        "voice_gender": ["여성 (선희)", "남성 (인준)"],
        "voice_ids": ["ko-KR-SunHiNeural", "ko-KR-InJoonNeural"],
        "ui": {
            "title": "카테고리", "text": "설명",
            "loading": "로딩 중...", "speed": "속도",
            "map_btn": "📍 지도 보기 (Google Map)",
            "intro": "안녕하세요. 메뉴를 소개해 드리겠습니다.",
            "toc": "목차입니다.",
            "outro": "천천히 골라주세요."
        }
    }
}

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
    return False

async def process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar, lang_key):
    tasks = []
    track_info_list = []
    
    for i, track in enumerate(menu_data):
        safe_title = sanitize_filename(track['title'])
        filename = f"{i+1:02}_{safe_title}.mp3"
        save_path = os.path.join(output_dir, filename)
        
        speech_text = track['text']
        # 2曲目以降（目次以外）は「番号、タイトル」を読み上げに含める
        if i > 0:
            if lang_key == "Japanese":
                speech_text = f"{i+1}、{track['title']}。\n{track['text']}"
            elif "English" in lang_key: # English (UK) に対応
                speech_text = f"Number {i+1}, {track['title']}.\n{track['text']}"
            else:
                speech_text = f"{i+1}, {track['title']}.\n{track['text']}"

        tasks.append(generate_single_track_fast(speech_text, save_path, voice_code, rate_value))
        track_info_list.append({"title": track['title'], "path": save_path})
    
    total = len(tasks)
    completed = 0
    for task in asyncio.as_completed(tasks):
        await task
        completed += 1
        progress_bar.progress(completed / total)
    return track_info_list

# HTMLプレイヤー生成
def create_standalone_html_player(store_name, menu_data, map_url, lang_key):
    ui = LANG_SETTINGS[lang_key]["ui"]
    
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
        <a href="{map_url}" target="_blank" style="text-decoration:none;">
            <button style="background-color:#4285F4; margin-bottom:10px;">{ui['map_btn']}</button>
        </a>
        """

    html_template = f"""<!DOCTYPE html>
<html lang="{LANG_SETTINGS[lang_key]['code']}"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>__STORE_NAME__</title>
<style>body{{font-family:sans-serif;background:#f4f4f4;margin:0;padding:20px;}}.c{{max-width:600px;margin:0 auto;background:#fff;padding:20px;border-radius:15px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
h1{{text-align:center;font-size:1.5em;color:#333;}}.box{{background:#fff5f5;border:2px solid #ff4b4b;border-radius:10px;padding:15px;text-align:center;margin-bottom:20px;}}
.ti{{font-size:1.3em;font-weight:bold;color:#ff4b4b;}}.ctrl{{display:flex;gap:10px;margin:15px 0;}}
button{{flex:1;padding:15px;font-size:1.2em;font-weight:bold;color:#fff;background:#ff4b4b;border:none;border-radius:10px;cursor:pointer;}}
.lst{{border-top:1px solid #eee;padding-top:10px;}}.itm{{padding:12px;border-bottom:1px solid #eee;cursor:pointer;}}.itm.active{{background:#ffecec;color:#ff4b4b;font-weight:bold;}}</style></head>
<body><div class="c"><h1>🎧 __STORE_NAME__</h1>
<div style="text-align:center;">__MAP_BUTTON__</div>
<div class="box"><div class="ti" id="ti">{ui['loading']}</div></div><audio id="au" style="width:100%"></audio>
<div class="ctrl"><button onclick="prev()">⏮</button><button onclick="toggle()" id="pb">▶</button><button onclick="next()">⏭</button></div>
<div style="text-align:center;margin-bottom:15px;">{ui['speed']}: <select id="sp" onchange="csp()"><option value="0.8">0.8</option><option value="1.0" selected>1.0</option><option value="1.2">1.2</option><option value="1.5">1.5</option></select></div>
<div id="ls" class="lst"></div></div>
<script>const pl=__PLAYLIST_JSON__;let idx=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');
function init(){{ren();ld(0);csp();}}
function ld(i){{idx=i;au.src=pl[idx].src;ti.innerText=pl[idx].title;ren();csp();}}
function toggle(){{if(au.paused){{au.play();pb.innerText="⏸";}}else{{au.pause();pb.innerText="▶";}}}}
function next(){{if(idx<pl.length-1){{ld(idx+1);au.play();pb.innerText="⏸";}}}}
function prev(){{if(idx>0){{ld(idx-1);au.play();pb.innerText="⏸";}}}}
function csp(){{au.playbackRate=parseFloat(document.getElementById('sp').value);}}
au.onended=function(){{if(idx<pl.length-1)next();else pb.innerText="▶";}};
function ren(){{const d=document.getElementById('ls');d.innerHTML="";pl.forEach((t,i)=>{{const m=document.createElement('div');m.className="itm "+(i===idx?"active":"");m.innerText=(i+1)+". "+t.title;m.onclick=()=>{{ld(i);au.play();pb.innerText="⏸";}};d.appendChild(m);}});}}
init();</script></body></html>"""
    
    final_html = html_template.replace("__STORE_NAME__", store_name)
    final_html = final_html.replace("__PLAYLIST_JSON__", playlist_json_str)
    final_html = final_html.replace("__MAP_BUTTON__", map_button_html)
    return final_html

# プレビュー表示（言語対応）
def render_preview_player(tracks, lang_key):
    ui = LANG_SETTINGS[lang_key]["ui"]
    playlist_data = []
    for track in tracks:
        if os.path.exists(track['path']):
            with open(track['path'], "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                playlist_data.append({"title": track['title'],"src": f"data:audio/mp3;base64,{b64}"})
    playlist_json = json.dumps(playlist_data)
    
    html_template = f"""<!DOCTYPE html><html><head><style>
    body{{margin:0;padding:0;font-family:sans-serif;}}
    .p-box{{border:2px solid #e0e0e0;border-radius:12px;padding:15px;background:#fcfcfc;text-align:center;}}
    .t-ti{{font-size:18px;font-weight:bold;color:#333;margin-bottom:10px;padding:10px;background:#fff;border-radius:8px;border-left:5px solid #ff4b4b;}}
    .ctrls{{display:flex;gap:5px;margin:10px 0;}}
    button{{flex:1;padding:10px;font-weight:bold;color:#fff;background:#ff4b4b;border:none;border-radius:5px;cursor:pointer;}}
    .lst{{text-align:left;max-height:150px;overflow-y:auto;border-top:1px solid #eee;margin-top:10px;padding-top:5px;}}
    .it{{padding:6px;border-bottom:1px solid #eee;cursor:pointer;font-size:14px;}}.it.active{{color:#ff4b4b;font-weight:bold;background:#ffecec;}}
    </style></head><body><div class="p-box"><div id="ti" class="t-ti">...</div><audio id="au" controls style="width:100%;height:30px;"></audio>
    <div class="ctrls"><button onclick="pv()">⏮</button><button onclick="tg()" id="pb">▶</button><button onclick="nx()">⏭</button></div>
    <div style="font-size:12px;color:#666;">{ui['speed']}:<select id="sp" onchange="sp()"><option value="0.8">0.8</option><option value="1.0" selected>1.0</option><option value="1.2">1.2</option><option value="1.5">1.5</option></select></div>
    <div id="ls" class="lst"></div></div>
    <script>
    const pl=__PLAYLIST__;let x=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');const ls=document.getElementById('ls');
    function init(){{rn();ld(0);sp();}}
    function ld(i){{x=i;au.src=pl[x].src;ti.innerText=pl[x].title;rn();sp();}}
    function tg(){{if(au.paused){{au.play();pb.innerText="⏸";}}else{{au.pause();pb.innerText="▶";}}}}
    function nx(){{if(x<pl.length-1){{ld(x+1);au.play();pb.innerText="⏸";}}}}
    function pv(){{if(x>0){{ld(x-1);au.play();pb.innerText="⏸";}}}}
    function sp(){{au.playbackRate=parseFloat(document.getElementById('sp').value);}}
    au.onended=function(){{if(x<pl.length-1)nx();else pb.innerText="▶";}};
    function rn(){{ls.innerHTML="";pl.forEach((t,i)=>{{const d=document.createElement('div');d.className="it "+(i===x?"active":"");d.innerText=(i+1)+". "+t.title;d.onclick=()=>{{ld(i);au.play();pb.innerText="⏸";}};ls.appendChild(d);}});}}
    init();</script></body></html>"""
    final_html = html_template.replace("__PLAYLIST__", playlist_json)
    components.html(final_html, height=400)

# --- UI ---
with st.sidebar:
    st.header("🔧 設定 / Settings")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🔑 API OK")
    else:
        api_key = st.text_input("Gemini API Key", type="password")
    
    # AIモデル選択
    valid_models = []
    target_model_name = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            all_models = list(genai.list_models())
            valid_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods]
            default_idx = next((i for i, n in enumerate(valid_models) if "flash" in n), 0)
            target_model_name = st.selectbox("AI Model", valid_models, index=default_idx)
        except: pass
    
    st.divider()
    
    # 言語選択
    st.subheader("🌐 言語 / Language")
    selected_lang = st.selectbox("作成する言語を選んでください", list(LANG_SETTINGS.keys()))
    current_lang_config = LANG_SETTINGS[selected_lang]
    
    # 声選択（言語に応じて変化）
    st.subheader("🗣️ 声 / Voice")
    voice_label = st.selectbox("Voice Type", current_lang_config["voice_gender"])
    voice_idx = current_lang_config["voice_gender"].index(voice_label)
    voice_code = current_lang_config["voice_ids"][voice_idx]
    
    # 速度固定
    rate_value = "+0%" if selected_lang != "Japanese" else "+40%"

st.title("🎧 Multilingual Menu Generator")

if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# Step 1
st.markdown("### 1. Store Info")
c1, c2 = st.columns(2)
with c1: store_name = st.text_input("🏠 店舗名 (Store Name)", placeholder="Cafe Tanaka")
with c2: menu_title = st.text_input("📖 メニュー名 (Menu Title)", placeholder="Lunch Menu / Lunch")
map_url = st.text_input("📍 Google Map URL", placeholder="https://maps.google.com/...")

st.markdown("---")

st.markdown("### 2. Upload Menu")
input_method = st.radio("Method", ("📂 Upload Images", "📷 Camera", "🌐 URL"), horizontal=True)

final_image_list = []
target_url = None

if input_method == "📂 Upload Images":
    uploaded_files = st.file_uploader("Images", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
    if uploaded_files: final_image_list.extend(uploaded_files)

elif input_method == "📷 Camera":
    if not st.session_state.show_camera:
        if st.button("Open Camera", type="primary"):
            st.session_state.show_camera = True
            st.rerun()
    else:
        camera_file = st.camera_input("Shoot", key=f"camera_{st.session_state.camera_key}")
        if camera_file:
            if st.button("Save & Next", type="primary"):
                st.session_state.captured_images.append(camera_file)
                st.session_state.camera_key += 1
                st.rerun()
        if st.button("Close"):
            st.session_state.show_camera = False
            st.rerun()
    if st.session_state.captured_images:
        if st.button("Clear All"):
            st.session_state.captured_images = []
            st.rerun()
        final_image_list.extend(st.session_state.captured_images)

elif input_method == "🌐 URL":
    target_url = st.text_input("URL", placeholder="https://...")

if input_method == "📂 Upload Images" and final_image_list:
    st.markdown("###### Check Images")
    cols = st.columns(5)
    for j, img in enumerate(final_image_list[:5]):
        with cols[j]: st.image(img, use_container_width=True)

st.markdown("---")

st.markdown("### 3. Generate Audio")
if st.button("🎙️ 生成開始 / Start Generating", type="primary", use_container_width=True):
    if not (api_key and target_model_name and store_name):
        st.error("Please check settings and store name."); st.stop()
    if not (final_image_list or target_url):
        st.warning("No images or URL."); st.stop()

    output_dir = os.path.abspath("menu_audio_output")
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    with st.spinner(f'Analyzing & Translating into {selected_lang}...'):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            parts = []
            
            # 言語ごとのプロンプト作成
            lang_instruction = ""
            if selected_lang == "Japanese":
                lang_instruction = "出力は全て日本語で行ってください。"
            elif "English" in selected_lang: # English (UK) に対応
                lang_instruction = "Translate all output into British English (UK). Currency should remain in Yen (e.g. 1000 Yen). Please use British spelling (e.g. colour, flavour)."
            elif selected_lang == "Chinese":
                lang_instruction = "Translate all output into Simplified Chinese. Currency should remain in Yen."
            elif selected_lang == "Korean":
                lang_instruction = "Translate all output into Korean. Currency should remain in Yen."

            prompt = f"""
            You are a professional menu accessibility expert.
            Analyze the menu images/text and organize them into 5-8 major categories.
            
            Important Rules:
            1. {lang_instruction}
            2. Group items intelligently (e.g., Appetizers, Main, Drinks).
            3. The 'text' field should be a reading script suitable for customers. Keep it rhythmic. Mention item name and price.
            4. Output MUST be valid JSON only.

            JSON Format:
            [
              {{"title": "Category Name", "text": "Reading script..."}},
              {{"title": "Category Name", "text": "Reading script..."}}
            ]
            """
            
            if final_image_list:
                parts.append(prompt)
                for f in final_image_list:
                    f.seek(0)
                    parts.append({"mime_type": f.type if hasattr(f, 'type') else 'image/jpeg', "data": f.getvalue()})
            elif target_url:
                web_text = fetch_text_from_url(target_url)
                if not web_text: st.error("URL Error"); st.stop()
                parts.append(prompt + f"\n\n{web_text[:30000]}")

            resp = None
            for _ in range(3):
                try: resp = model.generate_content(parts); break
                except exceptions.ResourceExhausted: time.sleep(5)
                except: pass

            if not resp: st.error("AI Error"); st.stop()

            text_resp = resp.text
            start = text_resp.find('[')
            end = text_resp.rfind(']') + 1
            if start == -1: st.error("Parse Error"); st.stop()
            menu_data = json.loads(text_resp[start:end])

            # イントロ・アウトロの追加（言語別）
            ui = current_lang_config["ui"]
            intro_t = f"{ui['intro']} {store_name}. "
            if menu_title: intro_t += f"{menu_title}. "
            intro_t += ui['toc']
            for i, tr in enumerate(menu_data):
                # 目次の読み上げ
                intro_t += f" {i+2}, {tr['title']}."
            intro_t += f" {ui['outro']}"
            
            menu_data.insert(0, {"title": ui['toc'].replace("です。", "").replace("Here is the ", "").replace("这是", "").replace("목차입니다.", "목차"), "text": intro_t})

            progress_bar = st.progress(0)
            st.info(f"Generating Audio ({selected_lang})...")
            generated_tracks = asyncio.run(process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar, selected_lang))

            html_str = create_standalone_html_player(store_name, generated_tracks, map_url, selected_lang)
            
            d_str = datetime.now().strftime('%Y%m%d')
            s_name = sanitize_filename(store_name)
            # ファイル名に言語コードを付与 (例: Cafe_en_2025...)
            zip_name = f"{s_name}_{current_lang_config['code']}_{d_str}.zip"
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
                "html_name": f"{s_name}_{current_lang_config['code']}_player.html",
                "tracks": generated_tracks,
                "lang_key": selected_lang
            }
            st.balloons()
        except Exception as e: st.error(f"Error: {e}")

if st.session_state.generated_result:
    res = st.session_state.generated_result
    st.divider()
    st.subheader("▶️ Preview")
    render_preview_player(res["tracks"], res["lang_key"])
    st.divider()
    st.subheader("📥 Download")
    
    st.info(f"Generated for: **{selected_lang}**")
    
    c1, c2 = st.columns(2)
    with c1: st.download_button(f"🌐 Web Player ({res['html_name']})", res['html_content'], res['html_name'], "text/html", type="primary")
    with c2: st.download_button(f"📦 ZIP File ({res['zip_name']})", data=res["zip_data"], file_name=res['zip_name'], mime="application/zip")
