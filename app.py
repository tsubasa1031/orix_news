import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import datetime

# ページ設定
st.set_page_config(
    page_title="オリックス・バファローズ ニュースまとめ",
    page_icon="⚾",
    layout="wide"
)

# --- 1. データ取得関数 (Google News RSSから取得) ---
@st.cache_data(ttl=1800)  # 30分間キャッシュしてアクセス負荷を軽減
def load_data():
    # Google News RSS検索 (キーワード: オリックス バファローズ)
    # hl=ja&gl=JP&ceid=JP:ja で日本のニュースを指定
    url = "https://news.google.com/rss/search?q=オリックス+バファローズ&hl=ja&gl=JP&ceid=JP:ja"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # XMLとしてパース (features="xml" を使用するには lxml が必要)
        # lxmlがない環境の場合は "html.parser" でも代用可能ですが、xml推奨
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        
        news_list = []
        for item in items:
            title = item.title.text
            link = item.link.text
            pub_date_str = item.pubDate.text
            description = item.description.text
            
            # 日付のフォーマット変換
            # RSSの日付形式 (例: Wed, 26 Nov 2025 ...) を扱いやすく変換
            try:
                pub_date = pd.to_datetime(pub_date_str).strftime('%Y-%m-%d %H:%M')
            except:
                pub_date = pub_date_str

            # descriptionにはHTMLが含まれる場合があるため、テキストのみ抽出して要約を作成
            summary_soup = BeautifulSoup(description, "html.parser")
            summary_text = summary_soup.get_text()[:80] + "..." if summary_soup.get_text() else "詳細はありません"

            # ニュース提供元をタイトルから抽出 (Google Newsの形式: "タイトル - 提供元")
            source = "News"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0] # 記事タイトル
                source = parts[1] # 提供元 (例: Yahoo!ニュース, 日刊スポーツ)

            news_list.append({
                "date": pub_date,
                "category": source, # 提供元をカテゴリとして利用
                "title": title,
                "summary": summary_text,
                "link": link,
                "tags": ["Web記事"]
            })
            
        return pd.DataFrame(news_list)

    except Exception as e:
        st.error(f"ニュースの取得に失敗しました: {e}")
        # エラー時のダミーデータ
        return pd.DataFrame([
            {"date": "-", "category": "Error", "title": "データ取得エラー", "summary": "再読み込みしてください。", "link": "#", "tags": []}
        ])

df = load_data()

# --- 2. サイドバー (フィルタリング) ---
st.sidebar.title("🔍 検索フィルター")

if not df.empty:
    # ニュース提供元（メディア）でフィルタリング
    categories = df["category"].unique()
    selected_categories = st.sidebar.multiselect(
        "メディアで絞り込み",
        categories,
        default=categories
    )
    
    # キーワード検索
    search_query = st.sidebar.text_input("キーワード検索 (例: 契約更改)")
    
    # フィルタリング実行
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
st.caption("Google News RSSより自動収集")

# 更新ボタン (キャッシュをクリアして再取得)
if st.button("ニュースを更新"):
    load_data.clear()
    st.rerun()

st.markdown(f"最新記事: **{len(filtered_df)}** 件")

# 表示モード切り替え
view_mode = st.radio("表示形式:", ["カード表示", "データテーブル"], horizontal=True)
st.divider()

if not filtered_df.empty:
    if view_mode == "カード表示":
        for index, row in filtered_df.iterrows():
            # 提供元を見出しに含めてExpanderを作成
            with st.expander(f"【{row['category']}】 {row['title']}", expanded=True):
                st.caption(f"📅 {row['date']}")
                st.write(row['summary'])
                # リンクボタンで記事へ飛ぶ
                st.link_button("記事を読む 🔗", row['link'])
                
    elif view_mode == "データテーブル":
        st.dataframe(
            filtered_df,
            column_config={
                "date": "日時",
                "category": "メディア",
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
