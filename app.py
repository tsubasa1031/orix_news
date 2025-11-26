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

# --- ヘルパー関数: キーワードからカテゴリを判定 ---
def assign_category(text):
    text = text.replace(" ", "")  # 空白除去してマッチングしやすくする
    keywords = {
        "契約・移籍": ["契約", "更改", "移籍", "FA", "トレード", "新加入", "退団", "戦力外", "ドラフト", "獲得", "ポスティング", "育成", "支配下", "年俸"],
        "怪我・調整": ["怪我", "故障", "手術", "離脱", "復帰", "調整", "抹消", "登録", "コンディション", "痛", "違和感"],
        "球団・イベント": ["ロゴ", "ユニフォーム", "イベント", "ファン", "チケット", "グッズ", "スポンサー", "マスコット", "キャンプ", "人事", "コーチ"],
        "試合・結果": ["試合", "勝", "負", "本塁打", "安打", "登板", "先発", "サヨナラ", "完封", "打率", "防御率", "スコア", "速報"]
    }
    
    for category, words in keywords.items():
        if any(word in text for word in words):
            return category
    return "その他ニュース"

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
        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item")
        
        news_list = []
        for item in items:
            title = item.title.text
            link = item.link.text
            pub_date_str = item.pubDate.text
            description = item.description.text
            
            # 日付のフォーマット変換
            try:
                pub_date = pd.to_datetime(pub_date_str).strftime('%Y-%m-%d %H:%M')
            except:
                pub_date = pub_date_str

            # descriptionにはHTMLが含まれる場合があるため、テキストのみ抽出して要約を作成
            summary_soup = BeautifulSoup(description, "html.parser")
            summary_text = summary_soup.get_text()[:100] + "..." if summary_soup.get_text() else "詳細はありません"

            # ニュース提供元をタイトルから抽出 (Google Newsの形式: "タイトル - 提供元")
            source = "News"
            clean_title = title
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                clean_title = parts[0] # 記事タイトル
                source = parts[1] # 提供元

            # 自動カテゴリ判定
            category = assign_category(clean_title + summary_text)

            news_list.append({
                "date": pub_date,
                "category": category,    # 自動判定した内容カテゴリ
                "media": source,         # メディア名
                "title": clean_title,
                "summary": summary_text,
                "link": link,
            })
            
        return pd.DataFrame(news_list)

    except Exception as e:
        st.error(f"ニュースの取得に失敗しました: {e}")
        # エラー時のダミーデータ
        return pd.DataFrame([
            {"date": "-", "category": "Error", "media": "-", "title": "データ取得エラー", "summary": "再読み込みしてください。", "link": "#"}
        ])

df = load_data()

# --- 2. サイドバー (フィルタリング) ---
st.sidebar.title("🔍 検索フィルター")

if not df.empty:
    # 内容カテゴリでフィルタリングに変更
    categories = sorted(df["category"].unique())
    
    # "その他ニュース" をリストの最後に移動するための処理
    if "その他ニュース" in categories:
        categories.remove("その他ニュース")
        categories.append("その他ニュース")

    selected_categories = st.sidebar.multiselect(
        "トピック（内容）で絞り込み",
        categories,
        default=categories
    )
    
    # キーワード検索
    search_query = st.sidebar.text_input("キーワード検索 (例: 吉田輝星)")
    
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
st.caption("Google News RSSより自動収集・分類")

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
            # カテゴリごとに色を変えるバッジ表示のようなイメージでExpanderを使用
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
