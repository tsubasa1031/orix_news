import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import time
import difflib
import re

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
        margin-bottom: 0.5rem;
    }
    .news-title:hover {
        color: #1f77b4;
        text-decoration: underline;
    }
    .news-meta {
        font-size: 0.8rem;
        color: #777;
    }
    .news-summary {
        font-size: 0.9rem;
        color: #444;
        line-height: 1.6;
        margin-top: 0.5rem;
    }
    
    /* カテゴリ別の色定義 */
    .cat-contract { background-color: #d32f2f; } /* 赤: 契約 */
    .cat-camp { background-color: #388e3c; }     /* 緑: キャンプ/練習 */
    .cat-event { background-color: #1976d2; }    /* 青: 球団/イベント */
    .cat-injury { background-color: #f57c00; }   /* オレンジ: 怪我 */
    .cat-other { background-color: #757575; }    /* グレー */

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
        .news-summary {
            color: #ccc;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# --- ヘルパー関数: カテゴリ判定の精度向上 ---
def assign_category(text):
    """
    ニュースのタイトル・本文からカテゴリを判定する。
    優先順位を設定して、より正確に分類する。
    """
    text = text.replace(" ", "")
    
    # カテゴリ定義 (上にあるものほど優先度が高い)
    categories = [
        {
            "name": "契約・移籍",
            "keywords": ["契約更改", "更改", "移籍", "FA", "トレード", "新加入", "退団", "戦力外", "ドラフト", "獲得", "ポスティング", "育成", "支配下", "年俸", "人的補償", "入団", "サイン", "残留"]
        },
        {
            "name": "怪我・調整",
            "keywords": ["怪我", "故障", "手術", "離脱", "全治", "リハビリ", "痛", "違和感", "コンディション", "病院", "検査"]
        },
        {
            "name": "キャンプ・練習", # オフシーズン向けに変更
            "keywords": ["キャンプ", "自主トレ", "練習", "ブルペン", "投げ込み", "打撃", "ノック", "紅白戦", "フェニックス", "秋季", "春季", "始動"]
        },
        {
            "name": "球団・イベント",
            "keywords": ["ファン感", "イベント", "ユニフォーム", "ロゴ", "チケット", "グッズ", "スポンサー", "マスコット", "人事", "コーチ", "監督", "ベストナイン", "ゴールデングラブ", "表彰", "パレード"]
        }
    ]
    
    for cat in categories:
        if any(word in text for word in cat["keywords"]):
            return cat["name"]
            
    return "その他ニュース"

def clean_summary(text):
    """
    RSSのdescriptionから余計なHTMLタグやゴミ文字を除去する
    """
    # HTMLタグの除去
    soup = BeautifulSoup(text, "html.parser")
    text = soup.get_text()
    
    # 連続する空白を1つに
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Google News特有の「記事を読む」などのリンク文字を削除
    text = text.replace("記事を読む", "").replace("Full coverage", "")
    
    # 文末の調整
    if len(text) > 100:
        text = text[:100] + "..."
        
    return text

# --- 1. データ取得関数 ---
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
                    
                    # フィルタリング
                    if "オリックス" not in title and "バファローズ" not in title and "中嶋" not in title and "岸田" not in title:
                         # 監督名などが含まれていれば通す、それ以外は厳しめに弾く
                         if "Bs" not in title: 
                            continue

                    link = item.link.text
                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    pub_date_str = item.pubDate.text
                    description = item.description.text
                    
                    # 日付処理 (JST変換)
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

                    # 要約のクリーニング
                    summary_text = clean_summary(description)
                    if not summary_text:
                        summary_text = "詳細はありません"

                    # 媒体名の抽出
                    source = "News"
                    clean_title = title
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        clean_title = parts[0]
                        source = parts[1]

                    # カテゴリ判定 (タイトルと要約の両方を使って判定)
                    category = assign_category(clean_title + summary_text)

                    all_news_list.append({
                        "timestamp": timestamp_jst,
                        "date": display_date,
                        "category": category,
                        "media": source,
                        "title": clean_title,
                        "summary": summary_text,
                        "link": link,
                    })
                
                time.sleep(0.5)

            except Exception as e:
                print(f"Query '{query}' failed: {e}")
                continue

    if not all_news_list:
        return pd.DataFrame([
            {"timestamp": pd.Timestamp.now(), "date": "-", "category": "Error", "media": "-", "title": "データ取得エラー", "summary": "再読み込みしてください。", "link": "#"}
        ])

    df = pd.DataFrame(all_news_list)
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)
    
    # 重複排除 (タイトル類似度)
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

df = load_data()

# --- 2. サイドバー ---
st.sidebar.title("🔍 検索フィルター")

sort_order = st.sidebar.radio("並び順", ["新しい順", "古い順"], horizontal=True)

if sort_order == "古い順":
    df = df.sort_values("timestamp", ascending=True).reset_index(drop=True)
else:
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)

if not df.empty:
    categories = sorted(df["category"].unique())
    # "その他ニュース"を最後に
    if "その他ニュース" in categories:
        categories.remove("その他ニュース")
        categories.append("その他ニュース")

    selected_categories = st.sidebar.multiselect(
        "トピック", categories, default=categories
    )
    
    search_query = st.sidebar.text_input("キーワード検索")
    
    filtered_df = df[df["category"].isin(selected_categories)]
    
    if search_query:
        filtered_df = filtered_df[
            filtered_df["title"].str.contains(search_query, case=False) | 
            filtered_df["summary"].str.contains(search_query, case=False)
        ]
else:
    filtered_df = df

# --- 3. メイン画面 ---
st.title("⚾ オリックス・バファローズ 最新ニュース")
st.caption("最新のニュースを自動収集して表示しています")

if st.button("🔄 ニュースを更新"):
    load_data.clear()
    st.rerun()

st.markdown("---")

if not filtered_df.empty:
    for index, row in filtered_df.iterrows():
        # カテゴリに応じたCSSクラス
        cat_class = "cat-other"
        if row['category'] == "契約・移籍": cat_class = "cat-contract"
        elif row['category'] == "怪我・調整": cat_class = "cat-injury"
        elif row['category'] == "球団・イベント": cat_class = "cat-event"
        elif row['category'] == "キャンプ・練習": cat_class = "cat-camp"

        link_url = row['link']
        
        st.markdown(f"""
        <div class="news-card">
            <div class="news-header">
                <span class="news-category {cat_class}">{row['category']}</span>
                <span class="news-meta">📅 {row['date']} | 🏢 {row['media']}</span>
            </div>
            <a href="{link_url}" target="_blank" class="news-title">{row['title']}</a>
            <div class="news-summary">{row['summary']}</div>
        </div>
        """, unsafe_allow_html=True)

else:
    st.warning("条件に一致するニュースが見つかりませんでした。")

# --- 4. フッター ---
st.markdown("---")
st.caption("Powered by Google News RSS")
