import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime
import time

# ページ設定
st.set_page_config(
    page_title="オリックス・バファローズ ニュースまとめ",
    page_icon="⚾",
    layout="wide"
)

# --- ヘルパー関数: キーワードからカテゴリを判定 ---
def assign_category(text):
    text = text.replace(" ", "")  # 空白除去してマッチングしやすくする
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
@st.cache_data(ttl=1800)  # 30分間キャッシュしてアクセス負荷を軽減
def load_data():
    # 情報量を増やすため、複数の切り口で検索を行う
    search_queries = [
        "オリックス+バファローズ",
        "オリックス+契約更改",
        "オリックス+移籍",
        "オリックス+新外国人",
        "オリックス+ファーム"
    ]
    
    all_news_list = []
    seen_links = set() # 重複排除用のセット
    
    with st.spinner('複数のソースからニュースを収集中...'):
        for query in search_queries:
            url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
            
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, "xml")
                items = soup.find_all("item")
                
                for item in items:
                    title = item.title.text
                    
                    # --- フィルタリング強化: 他球団情報の除外 ---
                    # タイトルに「オリックス」または「バファローズ」が含まれていない場合はスキップ
                    # (Google Newsは関連性の低い記事も拾うことがあるため、ここで厳密に判定します)
                    if "オリックス" not in title and "バファローズ" not in title:
                        continue

                    link = item.link.text
                    
                    if link in seen_links:
                        continue
                    seen_links.add(link)

                    pub_date_str = item.pubDate.text
                    description = item.description.text
                    
                    # --- 日付処理の改善 ---
                    # RSSの日付文字列をdatetimeオブジェクトに変換（ソート用）
                    try:
                        timestamp = pd.to_datetime(pub_date_str)
                        # タイムゾーンを日本時間に変換（Google NewsはGMTの場合が多い）
                        if timestamp.tzinfo is not None:
                            timestamp = timestamp.tz_convert('Asia/Tokyo')
                        display_date = timestamp.strftime('%Y-%m-%d %H:%M')
                    except:
                        timestamp = datetime.datetime.now()
                        display_date = pub_date_str

                    # descriptionのHTML除去と要約作成
                    summary_soup = BeautifulSoup(description, "html.parser")
                    summary_text = summary_soup.get_text()[:100] + "..." if summary_soup.get_text() else "詳細はありません"

                    # ニュース提供元抽出
                    source = "News"
                    clean_title = title
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        clean_title = parts[0]
                        source = parts[1]

                    category = assign_category(clean_title + summary_text)

                    all_news_list.append({
                        "timestamp": timestamp,   # ソート用のdatetimeオブジェクト
                        "date": display_date,     # 表示用の文字列
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
    
    # --- 時系列ソート ---
    # timestampカラムを使って新しい順（降順）にソート
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)
        
    return df

df = load_data()

# --- 2. サイドバー (フィルタリング) ---
st.sidebar.title("🔍 検索フィルター")

# ソート順の切り替え機能を追加
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
        "トピック（内容）で絞り込み",
        categories,
        default=categories
    )
    
    search_query = st.sidebar.text_input("キーワード検索 (例: 吉田輝星)")
    
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
st.caption("Google News RSSより自動収集・分類（複数ソース統合版）")

if st.button("ニュースを更新"):
    load_data.clear()
    st.rerun()

st.markdown(f"最新記事: **{len(filtered_df)}** 件")

view_mode = st.radio("表示形式:", ["カード表示", "データテーブル"], horizontal=True)
st.divider()

if not filtered_df.empty:
    if view_mode == "カード表示":
        for index, row in filtered_df.iterrows():
            label_prefix = ""
            if row['category'] == "契約・移籍":
                label_prefix = "💰"
            elif row['category'] == "怪我・調整":
                label_prefix = "🏥"
            elif row['category'] == "球団・イベント":
                label_prefix = "🏟️"
            elif row['category'] == "試合・結果":
                label_prefix = "⚾"
            else:
                label_prefix = "📰"

            with st.expander(f"{label_prefix} 【{row['category']}】 {row['title']}", expanded=True):
                st.caption(f"📅 {row['date']} | 🏢 {row['media']}")
                st.write(row['summary'])
                st.link_button("記事を読む 🔗", row['link'])
                
    elif view_mode == "データテーブル":
        st.dataframe(
            filtered_df,
            column_config={
                "date": "日時",
                "category": "トピック",
                "media": "メディア",
                "title": "見出し",
                "summary": "要約",
                "link": st.column_config.LinkColumn("リンク", display_text="記事を開く")
            },
            use_container_width=True,
            hide_index=True
        )
else:
    st.warning("条件に一致するニュースが見つかりませんでした。")

# --- 4. フッター ---
st.markdown("---")
st.caption("Powered by Google News RSS")
