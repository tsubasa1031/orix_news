import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import time
import difflib
import re
import json

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
        align-items: baseline;
        margin-bottom: 0.5rem;
    }
    .news-category {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: bold;
        color: white;
        margin-right: 0.5rem;
    }
    .news-title {
        font-size: 1.15rem;
        font-weight: bold;
        color: #333;
        text-decoration: none;
        display: block;
        margin-bottom: 0.2rem;
    }
    .news-title:hover {
        color: #1f77b4;
        text-decoration: underline;
    }
    .news-meta {
        font-size: 0.8rem;
        color: #777;
    }
    
    /* カテゴリ別の色定義 */
    .cat-contract { background-color: #d32f2f; }      /* 赤: 契約更改 */
    .cat-transfer { background-color: #c2185b; }      /* ピンク: 移籍/退団 */
    .cat-draft { background-color: #7b1fa2; }         /* 紫: ドラフト/新人 */
    .cat-award { background-color: #fbc02d; color: #333 !important; } /* 金: タイトル */
    .cat-camp { background-color: #388e3c; }          /* 緑: キャンプ/練習 */
    .cat-game { background-color: #0288d1; }          /* 水色: 試合 */
    .cat-event { background-color: #1976d2; }         /* 青: 球団/イベント */
    .cat-injury { background-color: #f57c00; }        /* オレンジ: 怪我 */
    .cat-other { background-color: #757575; }         /* グレー */

    @media (prefers-color-scheme: dark) {
        .news-card {
            background-color: #262730;
            border-color: #444;
        }
        .news-title {
            color: #eee;
        }
        .news-title:hover {
            color: #64b5f6;
        }
        .news-meta {
            color: #aaa;
        }
        .cat-award { color: #000 !important; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. 標準機能によるカテゴリ判定 (初期表示用・APIなし用) ---
def assign_category_simple(text):
    text = text.replace(" ", "")
    # 簡易版カテゴリ定義
    categories = [
        {"name": "タイトル受賞", "keywords": ["ベストナイン", "ゴールデングラブ", "表彰", "受賞", "MVP", "新人王"]},
        {"name": "契約・移籍", "keywords": ["契約更改", "更改", "移籍", "FA", "トレード", "退団", "戦力外", "ドラフト", "獲得", "年俸", "サイン", "残留", "万円", "億円"]},
        {"name": "怪我・調整", "keywords": ["怪我", "故障", "手術", "離脱", "リハビリ", "痛", "違和感", "病院"]},
        {"name": "キャンプ・練習", "keywords": ["キャンプ", "自主トレ", "練習", "ブルペン", "始動"]},
        {"name": "球団・イベント", "keywords": ["ファン感", "イベント", "ユニフォーム", "ロゴ", "チケット", "人事", "コーチ"]}
    ]
    for cat in categories:
        if any(word in text for word in cat["keywords"]):
            return cat["name"]
    return "その他"

# --- 2. AIによる一括カテゴリ判定 (Gemini API) ---
def categorize_batch_with_ai(news_df, api_key):
    """
    ニュースのタイトルリストを一括でAIに送信し、詳細なカテゴリを判定させる
    """
    if not HAS_GENAI:
        st.error("google-generativeai ライブラリがありません。")
        return news_df

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # タイトルとIDのリストを作成
    titles_data = []
    for idx, row in news_df.iterrows():
        titles_data.append({"id": idx, "title": row['title']})

    # バッチサイズ (一度に処理する件数)
    BATCH_SIZE = 30
    
    # プログレスバー
    progress_bar = st.progress(0)
    
    # チャンクごとに処理
    for i in range(0, len(titles_data), BATCH_SIZE):
        chunk = titles_data[i:i + BATCH_SIZE]
        
        # プロンプト作成 (定義を厳格化)
        prompt = f"""
        あなたはプロ野球ニュースの編集者です。
        以下のJSON形式のニュースタイトルリストを読み、それぞれの記事を最も適切なカテゴリに分類してください。
        判断に迷う場合は無理に分類せず「その他」を選択してください。
        
        【カテゴリ定義と判定基準】
        1. 契約更改
           - 対象: 既存選手の来季契約、年俸交渉、サイン、現状維持、アップ、ダウン。
           - 除外: FA宣言、退団、移籍、新外国人獲得はここには含めない。
        
        2. 移籍・退団
           - 対象: FA権行使、他球団への移籍、新外国人獲得、戦力外通告、自由契約、退団、ポスティングシステム。
           - 除外: ドラフト指名はここには含めない。
        
        3. ドラフト・新人
           - 対象: ドラフト会議での指名、指名挨拶、仮契約、新入団選手発表会見、ルーキーの紹介。
           - 除外: 新外国人選手は「移籍・退団」へ。
        
        4. 怪我・調整
           - 対象: 手術、リハビリ、怪我の診断結果、登録抹消（怪我理由）、コンディション不良、別メニュー調整。
        
        5. キャンプ・練習
           - 対象: 春季/秋季キャンプ、自主トレ公開、ブルペン入り、打撃練習、練習試合、紅白戦。
           - 除外: 公式戦の試合結果は含めない。
        
        6. タイトル受賞
           - 対象: ベストナイン、ゴールデングラブ、MVP、新人王、月間MVP、各種表彰。
        
        7. 試合・結果
           - 対象: 公式戦、交流戦、CS、日本シリーズの勝敗・スコア・試合経過。
           - 除外: 練習試合、紅白戦は「キャンプ・練習」へ。
        
        8. 球団・イベント
           - 対象: ユニフォーム発表、ロゴ変更、ファン感謝デー、チケット販売、コーチ就任・退任などの人事、マスコット、グッズ。
        
        9. その他
           - 上記のいずれにも明確に当てはまらないもの。
        
        【入力データ】
        {json.dumps(chunk, ensure_ascii=False)}
        
        【出力形式】
        以下のJSONフォーマットのリストのみを出力してください。Markdownのコードブロック(```jsonなど)は含めないでください。
        [
            {{"id": 0, "category": "契約更改"}},
            {{"id": 1, "category": "怪我・調整"}}
        ]
        """
        
        try:
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Markdownのコードブロックがあれば削除
            if result_text.startswith("```"):
                result_text = result_text.replace("```json", "").replace("```", "").strip()
            
            # JSONパース
            results = json.loads(result_text)
            
            # 結果をDataFrameに反映
            for res in results:
                idx = res.get("id")
                category = res.get("category")
                if idx is not None and category:
                    # インデックスが存在することを確認して更新
                    if idx in news_df.index:
                        news_df.at[idx, 'category'] = category
                        
        except Exception as e:
            print(f"Batch processing failed: {e}")
            # エラー時はスキップ（元のカテゴリのまま）
        
        # 進捗更新
        progress_bar.progress(min((i + BATCH_SIZE) / len(titles_data), 1.0))
        time.sleep(1) # 安全のため少し待機

    progress_bar.empty()
    return news_df

def clean_summary(text):
    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text()
    text = re.sub(r'\s+', ' ', text).strip()
    text = text.replace("記事を読む", "").replace("Full coverage", "")
    if len(text) > 100:
        text = text[:100] + "..."
    return text

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
    
    with st.spinner('ニュースを収集中...'):
        for query in search_queries:
            url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
            
            try:
                response = requests.get(url, timeout=10)
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

                    # 初期カテゴリ判定（キーワードベース）
                    category = assign_category_simple(clean_title)

                    all_news_list.append({
                        "timestamp": timestamp_jst,
                        "date": display_date,
                        "category": category, # 後でAIで上書き可能
                        "media": source,
                        "title": clean_title,
                        "link": link,
                    })
                
                time.sleep(0.5)

            except Exception as e:
                print(f"Query '{query}' failed: {e}")
                continue

    if not all_news_list:
        return pd.DataFrame([{"timestamp": pd.Timestamp.now(), "date": "-", "category": "Error", "media": "-", "title": "データ取得エラー", "link": "#"}])

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
if 'news_df' not in st.session_state:
    st.session_state.news_df = load_data()

# サイドバー設定
st.sidebar.title("🔍 設定・検索")

# APIキーを内部で保持（隠蔽）
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
        if st.button("✨ AIでカテゴリ細分化"):
            if not st.session_state.news_df.empty:
                with st.spinner("AIがタイトルを分析してカテゴリを振り分けています..."):
                    # データフレームごと渡して更新
                    updated_df = categorize_batch_with_ai(st.session_state.news_df.copy(), API_KEY)
                    st.session_state.news_df = updated_df
                    st.success("カテゴリの細分化が完了しました！")
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
    categories = sorted(df["category"].unique())
    if "その他" in categories:
        categories.remove("その他")
        categories.append("その他")

    selected_categories = st.sidebar.multiselect(
        "カテゴリで絞り込み", categories, default=categories
    )
    
    search_query = st.sidebar.text_input("キーワード検索")
    
    filtered_df = df[df["category"].isin(selected_categories)]
    
    if search_query:
        filtered_df = filtered_df[
            filtered_df["title"].str.contains(search_query, case=False)
        ]
else:
    filtered_df = df

# --- メイン画面 ---
st.title("⚾ オリックス・バファローズ 最新ニュース")
st.caption("最新のニュースを自動収集して表示しています")
st.markdown("---")

if not filtered_df.empty:
    for index, row in filtered_df.iterrows():
        # カテゴリに応じたCSSクラス
        cat_class = "cat-other"
        cat = row['category']
        if "契約" in cat or "年俸" in cat: cat_class = "cat-contract"
        elif "移籍" in cat or "退団" in cat or "FA" in cat: cat_class = "cat-transfer"
        elif "ドラフト" in cat or "新人" in cat: cat_class = "cat-draft"
        elif "タイトル" in cat or "表彰" in cat: cat_class = "cat-award"
        elif "怪我" in cat or "調整" in cat: cat_class = "cat-injury"
        elif "球団" in cat or "イベント" in cat: cat_class = "cat-event"
        elif "キャンプ" in cat or "練習" in cat: cat_class = "cat-camp"
        elif "試合" in cat: cat_class = "cat-game"

        link_url = row['link']
        
        st.markdown(f"""
        <div class="news-card">
            <div class="news-header">
                <span class="news-category {cat_class}">{row['category']}</span>
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
