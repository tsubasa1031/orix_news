import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import time
import difflib

# ページ設定
st.set_page_config(
    page_title="オリックス・バファローズ ニュースまとめ",
    page_icon="⚾",
    layout="wide"
)

# --- カスタムCSS: カード表示のデザイン調整 ---
st.markdown("""
    <style>
    .news-card {
        padding: 1.5rem;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 1rem;
        background-color: #ffffff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .news-title {
        font-size: 1.2rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
        text-decoration: none;
    }
    .news-meta {
        font-size: 0.85rem;
        color: #666;
        margin-bottom: 0.5rem;
    }
    .news-summary {
        font-size: 0.95rem;
        color: #333;
        line-height: 1.5;
    }
    /* ダークモード対応 */
    @media (prefers-color-scheme: dark) {
        .news-card {
            background-color: #262730;
            border-color: #444;
        }
        .news-title {
            color: #64b5f6;
        }
        .news-meta {
            color: #aaa;
        }
        .news-summary {
            color: #eee;
        }
    }
    </style>
    """, unsafe_allow_html=True)

# --- ヘルパー関数: キーワードからカテゴリを判定 ---
def assign_category(text):
    text = text.replace(" ", "")
    keywords = {
        "契約・移籍": ["契約", "更改", "移籍", "FA", "トレード", "新加入", "退団", "戦力外", "ドラフト", "獲得", "ポスティング", "育成", "支配下", "年俸", "人的補償"],
        "怪我・調整": ["怪我", "故障", "手術", "離脱", "復帰", "調整", "抹消", "登録", "コンディション", "痛", "違和感", "リハビリ"],
        "球団・イベント": ["ロゴ", "ユニフォーム", "イベント", "ファン", "チケット", "グッズ", "スポンサー", "マスコット", "キャンプ", "人事", "コーチ", "監督"],
        "試合・結果": ["試合", "勝", "負", "本塁打", "安打", "登板", "先発", "サヨナラ", "完封", "打率", "防御率", "スコア", "速報", "紅白戦"]
    }
    
    for category, words in keywords.items():
        if any(word in text for word in words):
            return category
    return "その他ニュース"

# --- 1. データ取得関数 (Google News RSSから取得) ---
@st.cache_data(ttl=1800)
def load_data():
    search_queries = [
        "オリックス+バファローズ",
        "オリックス+契約更改",
        "オリックス+移籍",
        "オリックス+新外国人",
        "オリックス+ファーム"
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
                    
                    if "オリックス" not in title and "バファローズ" not in title:
                        continue

                    link = item.link.text
                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    pub_date_str = item.pubDate.text
                    description = item.description.text
                    
                    # --- 日付処理の修正 (UTC -> JST) ---
                    try:
                        # まずpandasでパース (Google RSSはGMT/UTC)
                        timestamp = pd.to_datetime(pub_date_str)
                        
                        # タイムゾーン情報がない場合はUTCとして扱う
                        if timestamp.tzinfo is None:
                            timestamp = timestamp.tz_localize('UTC')
                        else:
                            # 既にある場合はUTCに統一
                            timestamp = timestamp.tz_convert('UTC')
                            
                        # 日本時間(Asia/Tokyo)に変換
                        timestamp_jst = timestamp.tz_convert('Asia/Tokyo')
                        display_date = timestamp_jst.strftime('%m/%d %H:%M') # 月/日 時:分
                    except:
                        timestamp_jst = pd.Timestamp.now(tz='Asia/Tokyo')
                        display_date = pub_date_str

                    summary_soup = BeautifulSoup(description, "html.parser")
                    summary_text = summary_soup.get_text()[:120] + "..." if summary_soup.get_text() else "詳細はありません"

                    source = "News"
                    clean_title = title
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        clean_title = parts[0]
                        source = parts[1]

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
    
    # 重複排除
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
st.caption("最新のニュースを自動収集・要約して表示しています")

if st.button("🔄 ニュースを更新"):
    load_data.clear()
    st.rerun()

st.markdown("---")

if not filtered_df.empty:
    for index, row in filtered_df.iterrows():
        # カテゴリに応じたアイコン
        icon = "📰"
        if row['category'] == "契約・移籍": icon = "💰"
        elif row['category'] == "怪我・調整": icon = "🏥"
        elif row['category'] == "球団・イベント": icon = "🏟️"
        elif row['category'] == "試合・結果": icon = "⚾"

        # URLリンク
        link_url = row['link']
        
        # カードレイアウトの表示 (HTML + CSS)
        # リンクをクリック可能なタイトルとして表示
        
        with st.container():
            col1, col2 = st.columns([1, 15])
            
            with col1:
                st.markdown(f"<div style='font-size: 2rem; text-align: center;'>{icon}</div>", unsafe_allow_html=True)
            
            with col2:
                # 記事カードのHTML生成
                st.markdown(f"""
                <div class="news-card">
                    <div class="news-meta">
                        <span style="font-weight:bold; color:#d9534f;">{row['category']}</span> | 
                        📅 {row['date']} | 🏢 {row['media']}
                    </div>
                    <a href="{link_url}" target="_blank" class="news-title">{row['title']} <span style="font-size:0.8em">🔗</span></a>
                    <div class="news-summary">{row['summary']}</div>
                </div>
                """, unsafe_allow_html=True)

else:
    st.warning("条件に一致するニュースが見つかりませんでした。")

# --- 4. フッター ---
st.markdown("---")
st.caption("Powered by Google News RSS")
