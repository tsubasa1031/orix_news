import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import time
import difflib
import re
import json
from collections import Counter

# --- 追加: Google Generative AI ライブラリ ---
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# ページ設定
st.set_page_config(
    page_title="オリックス・バファローズ ニュースまとめ",
    page_icon="⚾",
    layout="wide"
)

# --- カスタムCSS: デザイン調整 ---
st.markdown("""
    <style>
    .news-card {
        padding: 1.2rem;
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        margin-bottom: 0.8rem;
        background-color: #ffffff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: box-shadow 0.2s;
    }
    .news-card:hover {
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .news-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 0.5rem;
        flex-wrap: wrap;
        gap: 0.5rem;
    }
    .tags-container {
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem;
    }
    .news-tag {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
        color: #333;
        background-color: #f0f0f0;
        border: 1px solid #ddd;
    }
    /* 特定のキーワードを含むタグの色分け */
    .tag-contract { background-color: #ffebee; color: #c62828; border-color: #ef9a9a; }
    .tag-transfer { background-color: #fce4ec; color: #880e4f; border-color: #f48fb1; }
    .tag-draft { background-color: #f3e5f5; color: #4a148c; border-color: #ce93d8; }
    .tag-game { background-color: #e1f5fe; color: #01579b; border-color: #81d4fa; }
    .tag-camp { background-color: #e8f5e9; color: #1b5e20; border-color: #a5d6a7; }
    .tag-award { background-color: #fffde7; color: #f57f17; border-color: #fff59d; }
    .tag-injury { background-color: #fff3e0; color: #e65100; border-color: #ffcc80; }
    
    .news-title {
        font-size: 1.15rem;
        font-weight: bold;
        color: #333;
        text-decoration: none;
        display: block;
        margin-top: 0.3rem;
        line-height: 1.4;
    }
    .news-title:hover {
        color: #1f77b4;
        text-decoration: underline;
    }
    .news-meta {
        font-size: 0.8rem;
        color: #777;
        margin-top: 0.3rem;
    }

    @media (prefers-color-scheme: dark) {
        .news-card {
            background-color: #262730;
            border-color: #444;
        }
        .news-title { color: #eee; }
        .news-title:hover { color: #64b5f6; }
        .news-meta { color: #aaa; }
        .news-tag { background-color: #444; color: #ddd; border-color: #555; }
        /* ダークモード時のタグ色（少し暗めに） */
        .tag-contract { background-color: #5c1b1b; color: #ffcdd2; border-color: #ef5350; }
        .tag-transfer { background-color: #4a1428; color: #f8bbd0; border-color: #ec407a; }
        .tag-draft { background-color: #3a1c42; color: #e1bee7; border-color: #ab47bc; }
        .tag-game { background-color: #1a3b4d; color: #b3e5fc; border-color: #29b6f6; }
        .tag-camp { background-color: #1b3e20; color: #c8e6c9; border-color: #66bb6a; }
        .tag-award { background-color: #4a3b0a; color: #fff9c4; border-color: #ffee58; }
        .tag-injury { background-color: #4e2c0c; color: #ffe0b2; border-color: #ffa726; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. 標準機能によるタグ生成 (APIなし用) ---
def generate_tags_simple(text):
    text_clean = text.replace(" ", "")
    tags = []
    
    # カテゴリ判定ロジック
    categories = [
        {"name": "契約更改", "keywords": ["契約更改", "更改", "年俸", "サイン", "現状維持", "アップ", "ダウン", "保留"]},
        {"name": "移籍・退団", "keywords": ["移籍", "FA", "トレード", "退団", "戦力外", "自由契約", "ポスティング", "新外国人"]},
        {"name": "ドラフト・新人", "keywords": ["ドラフト", "指名", "入団", "新人", "ルーキー"]},
        {"name": "怪我・調整", "keywords": ["怪我", "故障", "手術", "離脱", "リハビリ", "痛", "違和感", "病院", "抹消"]},
        {"name": "キャンプ・練習", "keywords": ["キャンプ", "自主トレ", "練習", "ブルペン", "始動", "紅白戦"]},
        {"name": "タイトル受賞", "keywords": ["ベストナイン", "ゴールデングラブ", "表彰", "受賞", "MVP", "新人王"]},
        {"name": "球団情報", "keywords": ["ファン感", "イベント", "ユニフォーム", "ロゴ", "チケット", "人事", "コーチ"]}
    ]
    
    for cat in categories:
        if any(word in text_clean for word in cat["keywords"]):
            tags.append(cat["name"])
            
    # 簡易的な選手名抽出 (代表的な選手のみ)
    famous_players = ["中嶋", "岸田", "宮城", "紅林", "山下", "吉田", "森友哉", "若月", "頓宮", "杉本", "平野", "山崎", "宇田川", "東", "曽谷"]
    for player in famous_players:
        if player in text_clean:
            tags.append(player)
            
    if not tags:
        tags.append("ニュース")
        
    return list(set(tags)) # 重複排除

# --- 2. AIによるタグ生成 (Gemini API) ---
def tag_batch_with_ai(news_df, api_key):
    """
    ニュースのタイトルリストを一括でAIに送信し、適切なタグ（選手名、トピックなど）を生成させる
    """
    if not HAS_GENAI:
        st.error("google-generativeai ライブラリがありません。")
        return news_df

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    titles_data = []
    for idx, row in news_df.iterrows():
        titles_data.append({"id": idx, "title": row['title']})

    BATCH_SIZE = 20 # 処理速度と精度のバランス
    
    progress_bar = st.progress(0)
    
    for i in range(0, len(titles_data), BATCH_SIZE):
        chunk = titles_data[i:i + BATCH_SIZE]
        
        # プロンプト: タイトルから複数のタグを抽出させる
        prompt = f"""
        あなたはプロ野球ニュースのタグ付け担当です。
        以下のニュースタイトルのリストから、それぞれの記事に適したタグ（キーワード）を抽出してください。
        
        【抽出ルール】
        1. **トピックタグ**: 以下のリストから該当するものを1つ以上選んでください。
           - 契約更改, 移籍・退団, ドラフト・新人, 怪我・調整, キャンプ・練習, タイトル受賞, 試合・結果, 球団情報
        2. **エンティティタグ**: 記事に登場する具体的な「選手名」「監督名」「相手球団名」を抽出してください（例: 宮城大弥, 岸田監督, 阪神）。
        3. **詳細タグ**: 具体的な内容があれば短く抽出してください（例: 1000万増, 離脱）。
        
        【入力データ (JSON)】
        {json.dumps(chunk, ensure_ascii=False)}
        
        【出力形式】
        以下のJSONフォーマットのリストのみを出力してください。Markdownタグは不要です。
        [
            {{"id": 0, "tags": ["宮城大弥", "契約更改", "1億超え"]}},
            {{"id": 1, "tags": ["山下舜平大", "怪我・調整", "腰痛"]}}
        ]
        """
        
        try:
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            if result_text.startswith("```"):
                result_text = result_text.replace("```json", "").replace("```", "").strip()
            
            results = json.loads(result_text)
            
            for res in results:
                idx = res.get("id")
                tags = res.get("tags")
                if idx is not None and tags and isinstance(tags, list):
                    if idx in news_df.index:
                        # 既存のタグをAI生成タグで上書き
                        news_df.at[idx, 'tags'] = tags
                        
        except Exception as e:
            print(f"Batch processing failed: {e}")
        
        progress_bar.progress(min((i + BATCH_SIZE) / len(titles_data), 1.0))
        time.sleep(1)

    progress_bar.empty()
    return news_df

# --- 3. データ取得関数 ---
@st.cache_data(ttl=1800)
def load_data():
    search_queries = [
        "オリックス+バファローズ",
        "オリックス+契約更改",
        "オリックス+移籍",
        "オリックス+ドラフト",
        "オリックス+キャンプ"
    ]
    
    all_news_list = []
    seen_links = set()
    
    # User-Agentを設定してブラウザからのアクセスに見せる
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    with st.spinner('ニュースを収集中...'):
        for query in search_queries:
            # URLエンコーディング対策として requests の params を使用するか、
            # 確実に動作させるために文字列構築時に注意する。
            # ここではシンプルにf-stringで構築するが、User-Agentが重要。
            url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){query}&hl=ja&gl=JP&ceid=JP:ja"
            
            try:
                # headersを追加
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, "xml")
                items = soup.find_all("item")
                
                for item in items:
                    title = item.title.text
                    
                    if "オリックス" not in title and "バファローズ" not in title and "中嶋" not in title and "岸田" not in title:
                         if "Bs" not in title: 
                            continue

                    link = item.link.text
                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    pub_date_str = item.pubDate.text
                    try:
                        timestamp = pd.to_datetime(pub_date_str)
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.tz_localize('UTC')
                        else:
                            timestamp = timestamp.tz_convert('UTC')
                        timestamp_jst = timestamp.tz_convert('Asia/Tokyo')
                        display_date = timestamp_jst.strftime('%m/%d %H:%M')
                    except:
                        timestamp_jst = pd.Timestamp.now(tz='Asia/Tokyo')
                        display_date = pub_date_str

                    source = "News"
                    clean_title = title
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        clean_title = parts[0]
                        source = parts[1]

                    # 初期タグ生成（キーワードベース）
                    tags = generate_tags_simple(clean_title)

                    all_news_list.append({
                        "timestamp": timestamp_jst,
                        "date": display_date,
                        "tags": tags, # リスト形式
                        "media": source,
                        "title": clean_title,
                        "link": link,
                    })
                
                time.sleep(0.5)

            except Exception as e:
                print(f"Query '{query}' failed: {e}")
                # st.error(f"エラー: {e}") # UIが崩れるのでログのみ
                continue

    if not all_news_list:
        return pd.DataFrame([{"timestamp": pd.Timestamp.now(), "date": "-", "tags": ["Error"], "media": "System", "title": "データ取得エラー: 再読み込みしてください", "link": "#"}])

    df = pd.DataFrame(all_news_list)
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)
    
    unique_indices = []
    titles = df["title"].tolist()
    for i in range(len(titles)):
        is_duplicate = False
        for j in unique_indices:
            similarity = difflib.SequenceMatcher(None, titles[i], titles[j]).ratio()
            if similarity > 0.6: 
                is_duplicate = True
                break
        if not is_duplicate:
            unique_indices.append(i)
    
    df = df.iloc[unique_indices].reset_index(drop=True)
    return df

# --- アプリケーション状態の管理 ---
# データの再読み込みチェック: 'tags' カラムがない場合（古いデータ形式）は強制的にリロード
if 'news_df' not in st.session_state or 'tags' not in st.session_state.news_df.columns:
    st.session_state.news_df = load_data()

# サイドバー設定
st.sidebar.title("🔍 設定・検索")

# APIキーを内部で保持
API_KEY = "AIzaSyCc-6JTVoHwkyoT071WBVVXd_F_6I5yA84"
    
sort_order = st.sidebar.radio("並び順", ["新しい順", "古い順"], horizontal=True)

# データ取得・更新
col1, col2 = st.columns([1, 2])
with col1:
    if st.button("🔄 ニュースを更新"):
        load_data.clear()
        st.session_state.news_df = load_data()
        st.rerun()

with col2:
    if HAS_GENAI and API_KEY:
        if st.button("✨ AIでタグ付け詳細化"):
            if not st.session_state.news_df.empty:
                # エラー行が含まれている場合は実行しない
                if "Error" in st.session_state.news_df.iloc[0]["tags"]:
                     st.error("有効なニュースデータがありません。")
                else:
                    with st.spinner("AIがタイトルを分析して詳細なタグを生成中..."):
                        updated_df = tag_batch_with_ai(st.session_state.news_df.copy(), API_KEY)
                        st.session_state.news_df = updated_df
                        st.success("タグの生成が完了しました！")
                        st.rerun()
    elif not HAS_GENAI:
        st.error("google-generativeai ライブラリが必要です")

# データフレーム取得
df = st.session_state.news_df.copy()

# ソート反映
if sort_order == "古い順":
    df = df.sort_values("timestamp", ascending=True).reset_index(drop=True)
else:
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)

# フィルタリング
if not df.empty:
    # 全タグのリストを作成
    all_tags = []
    # ここでエラーになるのを防ぐため、tagsカラムが存在することを保証済み
    for tags in df['tags']:
        if isinstance(tags, list):
            all_tags.extend(tags)
        else:
            # 万が一リストでない場合（古いキャッシュなど）の安全策
            all_tags.append(str(tags))
    
    # 出現回数順にソートしてユニーク化
    tag_counts = Counter(all_tags)
    sorted_tags = [tag for tag, count in tag_counts.most_common()]

    selected_tags = st.sidebar.multiselect(
        "タグで絞り込み (選手名、トピックなど)", sorted_tags
    )
    
    search_query = st.sidebar.text_input("キーワード検索")
    
    # フィルタリングロジック
    if selected_tags:
        # 選択されたタグのいずれかを含んでいる行を抽出
        df = df[df['tags'].apply(lambda x: any(tag in x for tag in selected_tags) if isinstance(x, list) else False)]
    
    if search_query:
        df = df[df["title"].str.contains(search_query, case=False)]
else:
    pass

# --- メイン画面 ---
st.title("⚾ オリックス・バファローズ 最新ニュース")
st.caption("最新のニュースを自動収集して表示しています")
st.markdown("---")

if not df.empty:
    for index, row in df.iterrows():
        tags = row['tags'] if isinstance(row['tags'], list) else []
        link_url = row['link']
        
        # タグのHTML生成
        tags_html = ""
        for tag in tags:
            # タグの内容に応じてクラスを付与
            tag_class = ""
            if "契約" in tag or "更改" in tag: tag_class = "tag-contract"
            elif "移籍" in tag or "退団" in tag: tag_class = "tag-transfer"
            elif "ドラフト" in tag or "新人" in tag: tag_class = "tag-draft"
            elif "怪我" in tag or "手術" in tag: tag_class = "tag-injury"
            elif "キャンプ" in tag or "練習" in tag: tag_class = "tag-camp"
            elif "タイトル" in tag or "賞" in tag: tag_class = "tag-award"
            elif "試合" in tag or "勝" in tag or "負" in tag: tag_class = "tag-game"
            
            tags_html += f'<span class="news-tag {tag_class}">{tag}</span>'

        st.markdown(f"""
        <div class="news-card">
            <div class="news-header">
                <div class="tags-container">
                    {tags_html}
                </div>
                <span class="news-meta">📅 {row['date']} | 🏢 {row['media']}</span>
            </div>
            <a href="{link_url}" target="_blank" class="news-title">{row['title']}</a>
        </div>
        """, unsafe_allow_html=True)

else:
    st.warning("条件に一致するニュースが見つかりませんでした。")

# --- フッター ---
st.markdown("---")
st.caption("Powered by Google News RSS")
