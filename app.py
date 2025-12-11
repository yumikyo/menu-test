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
            await asyncio.sleep(1) # 短い待機で即リトライ
    
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

    # 全トラックのタスクを一気に登録（制限なし）
    for i, track in enumerate(menu_data):
        safe_title = sanitize_filename(track['title'])
        filename = f"{i+1:02}_{safe_title}.mp3"
        save_path = os.path.join(output_dir, filename)
        
        speech_text = track['text']
        if i > 0: speech_text = f"{i+1}、{track['title']}。\n{track['text']}"
        
        # タスクリストに追加（待機なしで次々登録）
        tasks.append(generate_single_track_fast(speech_text, save_path, voice_code, rate_value))
        
        # 結果用データ（順序保持のためここで作成）
        track_info_list.append({"title": track['title'], "path": save_path})

    total = len(tasks)
    completed = 0
    
    # ヨーイドン！で全タスク並列実行
    for task in asyncio.as_completed(tasks):
        await task
        completed += 1
        progress_bar.progress(completed / total)
    
    return track_info_list

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
    
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{store_name}</title>
<style>body{{font-family:sans-serif;background:#f4f4f4;margin:0;padding:20px;}}.c{{max-width:600px;margin:0 auto;background:#fff;padding:20px;border-radius:15px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
h1{{text-align:center;font-size:1.5em;color:#333;}}.box{{background:#fff5f5;border:2px solid #ff4b4b;border-radius:10px;padding:15px;text-align:center;margin-bottom:20px;}}
.ti{{font-size:1.3em;font-weight:bold;color:#ff4b4b;}}.ctrl{{display:flex;gap:10px;margin:15px 0;}}
button{{flex:1;padding:15px;font-size:1.2em;font-weight:bold;color:#fff;background:#ff4b4b;border:none;border-radius:10px;cursor:pointer;}}
.lst{{border-top:1px solid #eee;padding-top:10px;}}.itm{{padding:12px;border-bottom:1px solid #eee;cursor:pointer;}}.itm.active{{background:#ffecec;color:#ff4b4b;font-weight:bold;}}</style></head>
<body><div class="c"><h1>🎧 {store_name}</h1><div class="box"><div class="ti" id="ti">Loading...</div></div><audio id="au" style="width:100%"></audio>
<div class="ctrl"><button onclick="prev()">⏮</button><button onclick="toggle()" id="pb">▶</button><button onclick="next()">⏭</button></div>
<div style="text-align:center;margin-bottom:15px;">速度: <select id="sp" onchange="csp()"><option value="1.0">1.0</option><option value="1.4" selected>1.4</option><option value="2.0">2.0</option></select></div>
<div id="ls" class="lst"></div></div>
<script>const pl={playlist_json_str};let idx=0;const au=document.getElementById('au');const ti=document.getElementById('ti');const pb=document.getElementById('pb');
function init(){{ren();ld(0);csp();}}
function ld(i){{idx=i;au.src=pl[idx].src;ti.innerText=pl[idx].title;ren();csp();}}
function toggle(){{if(au.paused){{au.play();pb.innerText="⏸";}}else{{au.pause();pb.innerText="▶";}}}}
function next(){{if(idx<pl.length-1){{ld(idx+1);au.play();pb.innerText="⏸";}}}}
function prev(){{if(idx>0){{ld(idx-1);au.play();pb.innerText="⏸";}}}}
function csp(){{au.playbackRate=parseFloat(document.getElementById('sp').value);}}
au.onended=function(){{if(idx<pl.length-1)next();else pb.innerText="▶";}};
function ren(){{const d=document.getElementById('ls');d.innerHTML="";pl.forEach((t,i)=>{{const m=document.createElement('div');m.className="itm "+(i===idx?"active
