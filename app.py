# ==========================================
# 修正版：ボタンクリック時の処理（リトライ機能付き）
# ==========================================
from google.api_core import exceptions # 追加のインポート

if st.button("🎙️ 音声メニューを作成する"):
    if not api_key or not target_model_name:
        st.error("設定を確認してください（APIキーまたはモデル）")
    elif not store_name:
        st.warning("⚠️ 店舗名を入力してください（ファイル名に使用します）")
    elif not uploaded_files:
        st.warning("⚠️ 画像をアップロードしてください")
    else:
        # フォルダのリセット
        output_dir = os.path.abspath("menu_audio_album")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

        with st.spinner('AIが画像を解析し、台本を作成中...'):
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(target_model_name)
                
                content_parts = []
                prompt = """
                あなたは視覚障害者のためのレストランメニュー読み上げのプロです。
                提供された画像を解析し、以下のJSON形式のみを出力してください。
                価格は「円」まで読み上げ、カテゴリー分けをしてください。
                Markdown記法は不要です。
                
                出力例:
                [
                    {"title": "前菜", "text": "まずは前菜のメニューです。..."},
                    {"title": "メイン料理", "text": "続いてメイン料理のご紹介です。..."}
                ]
                """
                content_parts.append(prompt)
                for f in uploaded_files:
                    content_parts.append({"mime_type": f.type, "data": f.getvalue()})

                # --- 【ここを修正】粘り強くリトライする処理 ---
                response = None
                retry_count = 0
                max_retries = 3 # 最大3回までやり直す
                
                while retry_count < max_retries:
                    try:
                        response = model.generate_content(content_parts)
                        break # 成功したらループを抜ける
                    except exceptions.ResourceExhausted:
                        # 429エラーが出たらここに来る
                        st.warning(f"⚠️ 混雑中のため待機しています... ({retry_count+1}/{max_retries})")
                        time.sleep(10) # 10秒待つ
                        retry_count += 1
                    except Exception as e:
                        raise e # その他のエラーはそのまま報告

                if response is None:
                    st.error("❌ 混雑が激しいため、時間を置いて再度お試しください。")
                    st.stop()
                # ---------------------------------------------

                text_resp = response.text
                
                start = text_resp.find('[')
                end = text_resp.rfind(']') + 1
                menu_data = json.loads(text_resp[start:end])

                # --- イントロダクション（目次）の自動生成 ---
                intro_title = "はじめに・目次"
                intro_text = f"こんにちは、{store_name}です。"
                if menu_title:
                    intro_text += f"ただいまより、{menu_title}をご紹介します。"
                
                intro_text += "今回の内容は以下の通りです。"
                
                for i, track in enumerate(menu_data):
                    intro_text += f"トラック{i+2}は、{track['title']}。"
                
                intro_text += "それでは、ごゆっくりお聴きください。"
                
                menu_data.insert(0, {"title": intro_title, "text": intro_text})
                
                st.success(f"✅ 台本完成！ 全{len(menu_data)}トラック（イントロ含む）を生成します。")
                
                progress_bar = st.progress(0)
                
                # 音声生成ループ
                for i, track in enumerate(menu_data):
                    track_number = f"{i+1:02}"
                    safe_title = sanitize_filename(track['title'])
                    filename = f"{track_number}_{safe_title}.mp3"
                    save_path = os.path.join(output_dir, filename)
                    
                    st.subheader(f"🎵 Track {track_number}: {track['title']}")
                    st.write(track['text'])
                    
                    method = asyncio.run(generate_audio_safe(track['text'], save_path, voice_code, rate_value))
                    
                    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                        st.audio(save_path)
                    else:
                        st.error("音声ファイルの生成に失敗しました")
                    
                    progress_bar.progress((i + 1) / len(menu_data))
                    time.sleep(0.5)

                # ZIP作成処理
                date_str = datetime.now().strftime('%Y%m%d')
                safe_store_name = sanitize_filename(store_name)
                zip_filename = f"{safe_store_name}_{date_str}.zip"
                
                with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(output_dir):
                        for file in files:
                            zipf.write(os.path.join(root, file), file)
                
                if os.path.getsize(zip_filename) > 0:
                    st.success(f"📦 ZIP作成完了: {zip_filename}")
                    with open(zip_filename, "rb") as fp:
                        st.download_button(
                            label=f"📥 {zip_filename} をダウンロード",
                            data=fp,
                            file_name=zip_filename,
                            mime="application/zip"
                        )

            except Exception as e:
                st.error("エラーが発生しました")
                st.write(f"詳細: {e}")
