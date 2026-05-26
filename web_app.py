import streamlit as st
import pandas as pd
import pymysql
import plotly.express as px
import streamlit as st
import datetime
import calendar
import numpy as np


# --- 1. page configuration ---
st.set_page_config(
    page_title="AI Expense Assistant",
    page_icon="💰",
    layout="wide"
)

st.title("📊 AI Expense Assistant | 個人財務儀表板")
st.markdown("---")

# --- 2. database configuration ---
DB_CONFIG = dict(st.secrets["mysql"])


def get_db_connection():
    config = DB_CONFIG.copy()
    if isinstance(config['password'], str):
        config['password'] = config['password'].encode('utf-8').decode('latin-1')
    
    return pymysql.connect(
        **config,
        ssl_verify_cert=True,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor 
    )


@st.cache_data(ttl=5)
def load_data():
    try:
        # create copy of DB_CONFIG to avoid modifying the original dictionary
        config = DB_CONFIG.copy()


        # make sure password is a string and properly encoded (pymysql can be picky about this)
        if isinstance(config['password'], str):
            config['password'] = config['password'].encode('utf-8').decode('latin-1')


        # 1. connect to the database with SSL verification enabled
        conn = pymysql.connect(
            **config,
            ssl_verify_cert=True,
            charset='utf8mb4'
        )


        # 2. double-check
        with conn.cursor() as cursor:
            cursor.execute("USE test;")

       

        # 3. reasonable query to fetch data (only non-zero amounts, sorted by date)
        query = "SELECT * FROM test.daily_expenses WHERE amount_original != 0 ORDER BY transaction_date DESC;"
        df = pd.read_sql(query, conn)
        conn.close()

       

        # 4. ensure 'amount_original' is numeric (in case of any data issues) and fill non-convertible values with 0
        if not df.empty:
            df['amount_original'] = pd.to_numeric(df['amount_original'], errors='coerce').fillna(0)

        return df

       

    except Exception as e:
        st.error(f"❌ Failed to connect to database 資料庫連線失敗: {e}")
        return pd.DataFrame()

   



# retrieve budget from database for the selected currency, if not found return default value
def get_budget_from_db(currency):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT budget_amount FROM budget_settings WHERE currency = %s", (currency,))
            result = cursor.fetchone()
        conn.close()
        return float(result['budget_amount']) if result else 2000.0
    except Exception as e:
        return 2000.0

# save the budget for the selected currency into the database
def save_budget_to_db(currency, amount):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "INSERT INTO budget_settings (currency, budget_amount) VALUES (%s, %s) ON DUPLICATE KEY UPDATE budget_amount = %s"
            cursor.execute(sql, (currency, amount, amount))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"❌ Failed to save budget 儲存預算失敗: {e}")
   



## --- 3. conduct data reading and cleaning ---
df = load_data()



if not df.empty:
    df['amount_original'] = pd.to_numeric(df['amount_original'], errors='coerce').fillna(0)


    # --- filter currency ---
    st.markdown("### 💱 Currency Selection | 選擇顯示幣別")
    available_currencies = df['currency'].unique().tolist()
    default_idx = available_currencies.index('CAD') if 'CAD' in available_currencies else 0
    selected_currency = st.radio("Current Currency | 目前結算幣別：", available_currencies, index=default_idx, horizontal=True)
    st.markdown("---")
    filtered_df = df[df['currency'] == selected_currency]


    # 1. empty state handling
    if 'budgets' not in st.session_state:
        st.session_state.budgets = {}



    # 2. switch case: if the selected currency doesn't have a budget in session state, initialize it with a default value (
    if selected_currency not in st.session_state.budgets:
        if selected_currency == 'TWD':
            st.session_state.budgets[selected_currency] = 30000.0 

        else:
            st.session_state.budgets[selected_currency] = 2000.0  




    with st.sidebar:
        st.header("⚙️ Settings | 設定與除錯")
        st.markdown("### 🎯 Budget Setup | 預算設定")

       
        db_budget = get_budget_from_db(selected_currency)


        with st.form(key=f'budget_form_{selected_currency}'):
            new_budget = st.number_input(
                f"Set {selected_currency} Budget | 設定本月預算：",
                min_value=0.0,
                value=db_budget,  
                step=100.0

            )

            submit_budget = st.form_submit_button(label="Save | 確定並儲存")

           

            if submit_budget:

                save_budget_to_db(selected_currency, new_budget)
                st.success(f"✅{selected_currency} Budget Saved! 預算已儲存！")
                st.rerun()

       
        monthly_budget = get_budget_from_db(selected_currency)


        st.write("---")

        if st.button("🔄 Refresh Data | 手動更新資料"):
            st.cache_data.clear()
            st.rerun()





           

    # --- 4. Data Board ---
    expense_df = filtered_df[~filtered_df['category'].isin(['收入', '轉帳'])]
    income_df = filtered_df[filtered_df['category'] == '收入']
    transfer_df = filtered_df[filtered_df['category'] == '轉帳']

   

    total_exp = expense_df['amount_original'].sum()
    total_inc = income_df['amount_original'].sum()
    transfer_net = transfer_df['amount_original'].sum()
    net_income = total_inc - total_exp + transfer_net



    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(f"Total Expense | 總支出 ({selected_currency})", f"{total_exp:,.2f}", delta_color="inverse")

    with col2:
        st.metric(f"Total Income | 總收入 ({selected_currency})", f"{total_inc:,.2f}")

    with col3:
        st.metric(f"Transfer Flow | 換匯流動 ({selected_currency})", f"{transfer_net:,.2f}", delta_color="normal")

    with col4:
        st.metric(f"Net Cash Flow | 本月淨流向 ({selected_currency})", f"{net_income:,.2f}", delta=f"{net_income:,.2f}")



    st.markdown("---")



    # prediction and insights section
    st.subheader("🔮 AI Prediction & Insights | 預測與消費洞察")


    today = datetime.date.today()
    _, days_in_month = calendar.monthrange(today.year, today.month)
    days_passed = today.day

   

    if days_passed > 0 and total_exp > 0:
        daily_run_rate = total_exp / days_passed
        projected_total = daily_run_rate * days_in_month
        target_daily_rate = monthly_budget / days_in_month

       

        p_col1, p_col2 = st.columns(2) 
        with p_col1:
            st.info(f"📈 **Current Run Rate | 目前日均花費:**\n\n{daily_run_rate:,.2f} {selected_currency} / Day\n\n*(Target | 每日目標: {target_daily_rate:,.2f})*")
        with p_col2:
            st.warning(f"🎯 **Projected Total | 本月預估總花費:**\n\n{projected_total:,.2f} {selected_currency}\n\n*(Budget | 總預算: {monthly_budget:,.2f})*")
        
        projected_balance = monthly_budget - projected_total
        st.markdown(f"#### 🎯 Budget Achievement | 預算達成率分析 (Target: {monthly_budget:,.0f} {selected_currency})")
        
        if projected_total > monthly_budget:
            overspend_amt = projected_total - monthly_budget
            st.error(f"🚨 **警告 WARNING:** At the current burn rate, you will **overspend by {overspend_amt:,.2f} {selected_currency}**!\n\n💡 建議檢視近日的高額開銷。")
        elif projected_total > (monthly_budget * 0.8):
            st.warning(f"⚠️ **注意 CAUTION:** Projected spending has reached the 80% budget threshold!")
        else:
            st.success(f"✅ **安全 SAFE:** Good pacing! Projected month-end balance is **{projected_balance:,.2f} {selected_currency}**.")
            
        current_spend_ratio = min(total_exp / monthly_budget, 1.0) if monthly_budget > 0 else 0.0
        st.write(f"Budget Consumed | 目前已消耗預算：**{current_spend_ratio * 100:.1f}%**")
        st.progress(current_spend_ratio)

    else:
        st.info("💡 Unlock AI prediction features by accumulating more of this month's spending 累積更多本月支出後，即可解鎖 AI 預測功能")

   

    st.markdown("---")




    # --- 5. Chart analysis ---
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("🍕 Expense by Category | 支出類別比例")
        if not expense_df.empty:
            morandi_colors = ['#8B9DA3', '#D5C7BC', '#A8A39D', '#C0C5C1', '#D4CFC9']
            

            chart_df = expense_df.copy()
            chart_display_map = {
                "飲食": "飲食 Food", "Food": "飲食 Food",
                "生活": "生活 Living", "Living": "生活 Living",
                "交通": "交通 Transport", "Transport": "交通 Transport",
                "購物": "購物 Shopping", "Shopping": "購物 Shopping",
                "娛樂": "娛樂 Entertainment", "Entertainment": "娛樂 Entertainment",
                "投資": "投資 Investment", "Investment": "投資 Investment",
                "學習": "學習 Learning", "Learning": "學習 Learning"
            }
            chart_df['category'] = chart_df['category'].replace(chart_display_map)


            fig_pie = px.pie(
                chart_df, 
                values='amount_original', 
                names='category', 
                hole=0.4, 
                color_discrete_sequence=morandi_colors 
            )
            
            fig_pie.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        st.subheader("📅 Daily & Cumulative Spend | 每日與累積支出走勢")
        if not expense_df.empty:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots
            
            daily_trend = expense_df.groupby('transaction_date')['amount_original'].sum().reset_index()
            daily_trend = daily_trend.sort_values('transaction_date', ascending=True)
            
            daily_trend['cumulative_amount'] = daily_trend['amount_original'].cumsum()
            daily_trend['transaction_date'] = daily_trend['transaction_date'].astype(str)
            
            fig_combo = make_subplots(specs=[[{"secondary_y": True}]])
            
            # bar chart: daily spend 
            fig_combo.add_trace(
                go.Bar(
                    x=daily_trend['transaction_date'],
                    y=daily_trend['amount_original'],
                    name="Daily Spend | 單日花費",
                    marker_color='#8B9DA3',  
                    marker_line_color='#4A4643',
                    marker_line_width=1,
                    opacity=0.85
                ),
                secondary_y=False,
            )
            
            # 📈 line chart: cumulative spend
            fig_combo.add_trace(
                go.Scatter(
                    x=daily_trend['transaction_date'],
                    y=daily_trend['cumulative_amount'],
                    name="Cumulative Amount | 累積總額",
                    mode='lines+markers',
                    line=dict(color='#6B655F', width=3), 
                    marker=dict(size=8, color='#F4F1ED', line=dict(width=2, color='#6B655F')) 
                ),
                secondary_y=True,
            )
            
           
            max_y = daily_trend['cumulative_amount'].max() * 1.1
            
            fig_combo.update_layout(
                xaxis=dict(type='category'), 
                hovermode="x unified",       
                margin=dict(l=20, r=20, t=20, b=20),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(
                    orientation="h",         
                    yanchor="bottom", y=1.02, 
                    xanchor="right", x=1
                )
            )
            
            fig_combo.update_yaxes(title_text="Daily Amount | 單日金額", secondary_y=False, showgrid=False, range=[0, max_y])
            fig_combo.update_yaxes(title_text="Cumulative Amount | 累積總額", secondary_y=True, showgrid=True, gridcolor='rgba(0,0,0,0.1)', range=[0, max_y])
            
            st.plotly_chart(fig_combo, use_container_width=True)
        else:
            st.info(" There is currently no trend data. 目前沒有趨勢資料，請新增一些支出後再查看圖表。")


    st.markdown("---")


    
    # --- 6. Transaction History ---
    st.subheader("📝 Transaction History | 完整記帳明細")
    styled_df = df[['display_id', 'transaction_date', 'item_description', 'category', 'amount_original', 'currency']].copy()
    styled_df.columns = ['ID 編號', 'Date 日期', 'Item 品項', 'Category 分類', 'Amount 金額', 'Currency 幣別']

    
    display_map = {
        "飲食": "飲食 Food", "Food": "飲食 Food",
        "生活": "生活 Living", "Living": "生活 Living",
        "交通": "交通 Transport", "Transport": "交通 Transport",
        "購物": "購物 Shopping", "Shopping": "購物 Shopping",
        "娛樂": "娛樂 Entertainment", "Entertainment": "娛樂 Entertainment",
        "投資": "投資 Investment", "Investment": "投資 Investment",
        "學習": "學習 Learning", "Learning": "學習 Learning",
        "收入": "收入 Income", "Income": "收入 Income",
        "轉帳": "轉帳 Transfer", "Transfer": "轉帳 Transfer"
    }
    styled_df['Category 分類'] = styled_df['Category 分類'].replace(display_map)

    # 金額小數點處理 (你原本的邏輯)
    styled_df['Amount 金額'] = styled_df['Amount 金額'].apply(
        lambda x: int(x) if x % 1 == 0 else round(x, 2)
    )
    
    # 確保日期格式為 datetime 以便篩選
    styled_df['Date 日期'] = pd.to_datetime(styled_df['Date 日期']).dt.date

    # 👇 4. 新增：日期篩選器 (Date Filter)
    col_filter, _ = st.columns([1, 1])
    with col_filter:
        today = datetime.date.today()
        first_day_of_month = today.replace(day=1)
        date_range = st.date_input(
            "📅 篩選日期範圍 (Select Date Range)：", 
            value=(first_day_of_month, today)
        )

    # 執行日期篩選邏輯
    if len(date_range) == 2:
        mask = (styled_df['Date 日期'] >= date_range[0]) & (styled_df['Date 日期'] <= date_range[1])
        styled_df = styled_df.loc[mask]
    elif len(date_range) == 1:
        mask = (styled_df['Date 日期'] >= date_range[0])
        styled_df = styled_df.loc[mask]

    


    styled_df['Amount 金額'] = styled_df['Amount 金額'].apply(
        lambda x: int(x) if x % 1 == 0 else round(x, 2)
    )

    # 👇 新增：計算篩選區間的總花費
    total_filtered_amount = styled_df['Amount 金額'].sum()
    
    # 取得目前的幣別字串 (如果表格有資料的話)
    current_currency = styled_df['Currency 幣別'].iloc[0] if not styled_df.empty else ""

    # 👇 升級排版：利用 columns 將「筆數」放左邊，「總花費」放右邊
    info_col1, info_col2 = st.columns([1, 1])
    with info_col1:
        st.caption(f"Showing {len(styled_df)} records | 共顯示 {len(styled_df)} 筆紀錄")
    with info_col2:
        # 使用 HTML/Markdown 讓金額靠右對齊，並用稍微醒目的顏色標示
        st.markdown(
            f"<div style='text-align: right;'>"
            f"<b>💰 區間總計 (Total)：<span style='color: #A0522D; font-size: 1.1em;'>{total_filtered_amount:,.2f} {current_currency}</span></b>"
            f"</div>", 
            unsafe_allow_html=True
        )

    
    def apply_morandi_table_style(styler):
        # 1. set the base style for the entire table (light beige background with soft gray-brown text)
        styler.set_properties(**{
            'background-color': "#F5EEE5",  
            'color': '#4A4643',             
            'border-bottom': '1px solid #E8E4D9' 
        })
        
        # 2. headers with a slightly darker background and bold text
        styler.set_table_styles([
            {
                'selector': 'th',  
                'props': [
                    ('background-color', '#B3C6C9'), 
                    ('color', '#4A4643'),            
                    ('font-weight', 'bold'),         
                    ('border-bottom', '1px solid #8B9DA3') 
                ]
            }
        ])
        return styler

    

    st.table(styled_df.style.pipe(apply_morandi_table_style).hide(axis="index"))


else:
    st.info("👋 歡迎！目前資料庫是空的。請在 LINE 機器人輸入第一筆帳務（例如：今天晚餐 20 加幣）後重新整理此頁面。")
    st.info("👀 Welcome! The database is currently empty. Please input your first transaction through the LINE bot (e.g., 'Spent 20 Canadian Dollars for dinner today') and refresh this page.")
