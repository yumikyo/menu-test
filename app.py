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
st.set_page_config(page_title="Menu Player Generator", layout="wide")

# ==========================================
# 1. 関数定義群
# ==========================================

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

# ★最速モード用：制限なし生成関数
async def generate_single_track_fast(text, filename, voice_code, rate_value):
    # EdgeTTS (非同期)
    for attempt in range(3):
        try:
            comm = edge_tts.Communicate(text, voice_code, rate=rate_value)
            await comm.save(filename)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                return True
        except:
            await asyncio.sleep(1)
    
    # GoogleTTS (予備)
    try:
        def gtts_task():
            tts = gTTS(text=text, lang='ja')
            tts.save(filename)
        await asyncio.to_thread(gtts_task)
        return True
    except:
        return False

# ★最速モード用：一括並列処理マネージャー
async def process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar):
    tasks = []
    track_info_list = []

    for i, track in enumerate(menu_data):
        safe_title = sanitize_filename(track['title'])
        filename = f"{i+1:02}_{safe_title}.mp3"
        save_path = os.path.join(output_dir, filename)
        
        speech_text = track['text']
        if i > 0: speech_text = f"{i+1}、{track['title']}。\n{track['text']}"
        
        tasks.append(generate_single_track_fast(speech_text, save_path, voice_code, rate_value))
        track_info_list.append({"title": track['title'], "path": save_path})

    total = len(tasks)
    completed = 0
    
    for task in asyncio.as_completed(tasks):
        await task
        completed += 1
        progress_bar.progress(completed / total)
    
    return track_info_list

# 【修正版】HTML生成関数（f-stringを使わず .replace で置換することでエラーを回避）
def create_standalone_html_player(store_name, menu_data):
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
    
    # CSSやJSの波括弧 { } がPythonと干渉しないように、通常の文字列として定義
    html_template = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>__STORE_NAME__</title>
<style>body{font-family:sans-serif;background:#f4f4f4;margin:0;padding:20px;}.c{max-width:600px;margin:0 auto;background:#fff;padding:20px;border-radius:15px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}
h1{text-align:center;font-size:1.5em;color:#333;}.box{background:#fff5f5;border:2px solid #ff4b4b;border-radius:10px;padding:15px;text-align:center;margin-bottom:20px;}
.ti{font-size:1.3em;font-weight:bold;color:#ff4b4b;}.ctrl{display:flex;gap:10px;margin:15px 0;}
button{flex:1;padding:15px;font-size:1.2em;font-weight:bold;color:#fff;background:#ff4b4b;border:none;border-radius:10px;cursor:pointer;}
.lst{border-top:1px solid #eee;padding-top:10px;}.itm{padding:12px;border-bottom:1px solid #eee;cursor:pointer;}.itm.active{background:#ffecec;color:#ff4b4b;font-weight:bold;}</style></head>
<body><div class="c"><h1>🎧 __STORE_NAME__</h1><div class="box"><div class="ti" id="ti">Loading...</div></div><audio id="au" style="width:100%"></audio>
<div class="ctrl"><button onclick="prev()">⏮</button><button onclick="toggle()" id="pb">▶</button><button onclick="next()">⏭</button></div>
<div style="text-align:center;margin-bottom:15px;">速度: <select id="sp" onchange="csp()"><option value="1.0">1.0</option><option value="1.4" selected>1.4</option><option value="2.0">2.0</option></select></div>
<div id="ls" class="lst"></div></div>
<script>const pl=__PLAYLIST_JSON__;let idx=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');
function init(){ren();ld(0);csp();}
function ld(i){idx=i;au.src=pl[idx].src;ti.innerText=pl[idx].title;ren();csp();}
function toggle(){if(au.paused){au.play();pb.innerText="⏸";}else{au.pause();pb.innerText="▶";}}
function next(){if(idx<pl.length-1){ld(idx+1);au.play();pb.innerText="⏸";}}
function prev(){if(idx>0){ld(idx-1);au.play();pb.innerText="⏸";}}
function csp(){au.playbackRate=parseFloat(document.getElementById('sp').value);}
au.onended=function(){if(idx<pl.length-1)next();else pb.innerText="▶";};
function ren(){const d=document.getElementById('ls');d.innerHTML="";pl.forEach((t,i)=>{const m=document.createElement('div');m.className="itm "+(i===idx?"active":"");m.innerText=(i+1)+". "+t.title;m.onclick=()=>{ld(i);au.play();pb.innerText="⏸";};d.appendChild(m);});}
init();</script></body></html>"""

    # ここで安全に置換する
    return html_template.replace("__STORE_NAME__", store_name).replace("__PLAYLIST_JSON__", playlist_json_str)

# 【修正版】プレビュー表示関数
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
    .t-ti{font-size:18px;font-weight:bold;color:#333;margin-bottom:10px;padding:10px;background:#fff;border-radius:8px;border-left:5px solid #ff4b4b;}
    .ctrls{display:flex;gap:5px;margin:10px 0;}
    button{flex:1;padding:10px;font-weight:bold;color:#fff;background:#ff4b4b;border:none;border-radius:5px;cursor:pointer;}
    .lst{text-align:left;max-height:150px;overflow-y:auto;border-top:1px solid #eee;margin-top:10px;padding-top:5px;}
    .it{padding:6px;border-bottom:1px solid #eee;cursor:pointer;font-size:14px;}.it.active{color:#ff4b4b;font-weight:bold;background:#ffecec;}
    </style></head><body><div class="p-box"><div id="ti" class="t-ti">...</div><audio id="au" controls style="width:100%;height:30px;"></audio>
    <div class="ctrls"><button onclick="pv()">⏮</button><button onclick="tg()" id="pb">▶</button><button onclick="nx()">⏭</button></div>
    <div style="font-size:12px;color:#666;">速度:<select id="sp" onchange="sp()"><option value="1.0">1.0</option><option value="1.4" selected>1.4</option><option value="2.0">2.0</option></select></div>
    <div id="ls" class="lst"></div></div>
    <script>
    const pl=__PLAYLIST__;let x=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');const ls=document.getElementById('ls');
    function init(){rn();ld(0);sp();}
    function ld(i){x=i;au.src=pl[x].src;ti.innerText=pl[x].title;rn();sp();}
    function tg(){if(au.paused){au.play();pb.innerText="⏸";}else{au.pause();pb.innerText="▶";}}
    function nx(){if(x<pl.length-1){ld(x+1);au.play();pb.innerText="⏸";}}
    function pv(){if(x>0){ld(x-1);au.play();pb.innerText="⏸";}}
    function sp(){au.playbackRate=parseFloat(document.getElementById('sp').value);}
    au.onended=function(){if(x<pl.length-1)nx();else pb.innerText="▶";};
    function rn(){ls.innerHTML="";pl.forEach((t,i)=>{const d=document.createElement('div');d.className="it "+(i===x?"active":"");d.innerText=(i+1)+". "+t.title;d.onclick=()=>{ld(i);au.play();pb.innerText="⏸";};ls.appendChild(d);});}
    init();</script></body></html>"""
    
    html_code = html_template.replace("__PLAYLIST__", playlist_json)
    components.html(html_code, height=400)

# 【修正版】シェアボタン関数
def render_share_button(html_content, file_name):
    b64_html = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    html_template = """
    <!DOCTYPE html><html><head><style>
    .share-btn {width:100%;padding:15px;background-color:#28a745;color:white;font-size:16px;font-weight:bold;border:none;border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px;}
    </style></head><body>
    <button class="share-btn" onclick="shareFile()">📤 プレイヤーをLINEなどで送る (共有)</button>
    <script>async function shareFile(){const b64="__B64__";const fileName="__FILENAME__";try{const byteCharacters=atob(b64);const byteNumbers=new Array(byteCharacters.length);for(let i=0;i<byteCharacters.length;i++){byteNumbers[i]=byteCharacters.charCodeAt(i);}const byteArray=new Uint8Array(byteNumbers);const blob=new Blob([byteArray],{type:"text/html"});const file=new File([blob],fileName,{type:"text/html"});if(navigator.share){await navigator.share({files:[file],title:'音声メニュー',text:'お店の音声メニューを送ります。'});}else{alert("ブラウザが対応していません。下のダウンロードボタンを使ってください。");}}catch(e){alert("共有失敗: "+e);}}</script></body></html>"""
    
    share_code = html_template.replace("__B64__", b64_html).replace("__FILENAME__", file_name)
    components.html(share_code, height=60)

# ==========================================
# 2. UI設定
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
    
    st.divider()
    st.subheader("🗣️ 音声設定")
    voice_options = {"女性（七海）": "ja-JP-NanamiNeural", "男性（慶太）": "ja-JP-KeitaNeural"}
    selected_voice = st.selectbox("声の種類", list(voice_options.keys()))
    voice_code = voice_options[selected_voice]
    rate_value = "+40%"

st.title("🎧 Menu Player Generator")
st.markdown("##### 視覚障害のある方のための「聴くメニュー」生成アプリ")

if 'captured_images' not in st.session_state: st.session_state.captured_images = []
if 'camera_key' not in st.session_state: st.session_state.camera_key = 0
if 'generated_result' not in st.session_state: st.session_state.generated_result = None
if 'show_camera' not in st.session_state: st.session_state.show_camera = False

# Step 1
st.markdown("### 1. お店情報の入力")
c1, c2 = st.columns(2)
with c1: store_name = st.text_input("🏠 店舗名（必須）", placeholder="例：カフェタナカ")
with c2: menu_title = st.text_input("📖 今回のメニュー名", placeholder="例：ランチ")
st.markdown("---")

# Step 2
st.markdown("### 2. メニューの登録方法を選ぶ")
input_method = st.radio("方法", ("📂 アルバムから", "📷 その場で撮影", "🌐 URL入力"), horizontal=True)

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
        st.info("""
        ⚠️ **カメラの使い方のヒント**
        * **インカメラになる場合**: カメラ画面内の「Select Device」や「回転マーク」で切り替えてください。
        * **ボタンの意味**: 「Take Photo」＝ 撮影、「Clear Photo」＝ 撮り直し
        """)
        camera_file = st.camera_input("📸 撮影（Take Photoを押してください）", key=f"camera_{st.session_state.camera_key}")
        if camera_file:
            if st.button("⬇️ この写真を追加して次を撮る", type="primary"):
                st.session_state.captured_images.append(camera_file)
                st.session_state.camera_key += 1
                st.rerun()
        st.markdown("---")
        if st.button("❌ カメラを閉じる"):
            st.session_state.show_camera = False
            st.rerun()

    if st.session_state.captured_images:
        st.markdown("#### 📸 撮影された写真リスト")
        for i, img in enumerate(st.session_state.captured_images):
            c_img, c_del = st.columns([1, 2])
            with c_img: st.image(img, width=100)
            with c_del:
                st.write(f"No.{i+1}")
                if st.button(f"🗑️ No.{i+1} を削除（とりなおす）", key=f"del_{i}"):
                    del st.session_state.captured_images[i]
                    st.rerun()
        st.divider()
        if st.button("🗑️ 全て削除して最初から"):
            st.session_state.captured_images = []
            st.rerun()
        final_image_list.extend(st.session_state.captured_images)

elif input_method == "🌐 URL入力":
    target_url = st.text_input("URL", placeholder="https://...")

if input_method == "📂 アルバムから" and final_image_list:
    st.markdown("###### ▼ 画像確認")
    cols = st.columns(len(final_image_list))
    for idx, img in enumerate(final_image_list):
        if idx < 5:
            with cols[idx]: st.image(img, caption=f"No.{idx+1}", use_container_width=True)
st.markdown("---")

# Step 3
st.markdown("### 3. 音声メニューの作成")
if st.button("🎙️ 作成開始", type="primary", use_container_width=True):
    if not (api_key and target_model_name and store_name):
        st.error("設定や店舗名を確認してください"); st.stop()
    if not (final_image_list or target_url):
        st.warning("画像かURLを入力してください"); st.stop()

    output_dir = os.path.abspath("menu_audio_album")
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    with st.spinner('解析中...'):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(target_model_name)
            parts = []
            
            prompt = """
            あなたは視覚障害者のためのメニュー読み上げデータ作成のプロです。
            以下のJSON形式のみ出力。Markdown不要。接続詞・挨拶削除。商品名と価格のみ。
            [{"title": "前菜", "text": "シーザーサラダ、800円。"}]
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

            # 変数を resp に統一
            text_resp = resp.text
            
            start = text_resp.find('[')
            end = text_resp.rfind(']') + 1
            if start == -1: st.error("解析エラー"); st.stop()
            menu_data = json.loads(text_resp[start:end])

            intro_t = f"こんにちは、{store_name}です。"
            if menu_title: intro_t += f"ただいまより{menu_title}をご紹介します。"
            intro_t += "目次です。"
            for i, tr in enumerate(menu_data): intro_t += f"{i+2}、{tr['title']}。"
            intro_t += "それでは、ごゆっくりお聴きください。"
            menu_data.insert(0, {"title": "はじめに・目次", "text": intro_t})

            progress_bar = st.progress(0)
            st.info("音声を生成しています... (並列処理中)")
            generated_tracks = asyncio.run(process_all_tracks_fast(menu_data, output_dir, voice_code, rate_value, progress_bar))

            html_str = create_standalone_html_player(store_name, generated_tracks)
            d_str = datetime.now().strftime('%Y%m%d')
            s_name = sanitize_filename(store_name)
            zip_name = f"{s_name}_{d_str}.zip"
            zip_path = os.path.abspath(zip_name)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
                for root, dirs, files in os.walk(output_dir):
                    for file in files: z.write(os.path.join(root, file), file)

            st.session_state.generated_result = {
                "zip_path": zip_path, "zip_name": zip_name,
                "html_content": html_str, "html_name": f"{s_name}_player.html",
                "tracks": generated_tracks
            }
            st.balloons()
        except Exception as e: st.error(f"エラー: {e}")

# Step 4
if st.session_state.generated_result:
    res = st.session_state.generated_result
    st.divider()
    st.subheader("▶️ プレビュー (その場で確認)")
    render_preview_player(res["tracks"])
    st.divider()
    st.subheader("📥 共有・保存")
    
    st.markdown("**📱 1. プレイヤーを直接送る (LINEなど)**")
    render_share_button(res['html_content'], res['html_name'])
    
    st.write("")
    st.markdown("**📥 2. ファイルとして保存**")
    c_w, c_z = st.columns(2)
    with c_w:
        st.download_button(f"🌐 Webプレイヤー ({res['html_name']})", res['html_content'], res['html_name'], "text/html")
    with c_z:
        st.download_button(f"📦 ZIPファイル ({res['zip_name']})", open(res["zip_path"], "rb"), res['zip_name'], "application/zip")
