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

EXCHANGE_RATES = {
    'TWD': 1.0,      
    'CAD': 23.5,     # 1 CAD ≈ 23.5 TWD
    'EUR': 34.8,     # 1 EUR ≈ 34.8 TWD
    'USD': 32.2,     # 1 USD ≈ 32.2 TWD
    'JPY': 0.21      # 1 JPY ≈ 0.21 TWD
}


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
                    ('background-color', "#C4D6D9"), 
                    ('color', '#4A4643'),            
                    ('font-weight', 'bold'),         
                    ('border-bottom', '1px solid #8B9DA3') 
                ]
            }
        ])
        return styler





## --- 3. conduct data reading and cleaning ---
df = load_data()

if not df.empty:
    df['amount_original'] = pd.to_numeric(df['amount_original'], errors='coerce').fillna(0)
    df['display_id'] = df['display_id'].astype(str)

    # --- filter currency ---
    st.markdown("### 💱 Currency Selection | 選擇顯示幣別")
    available_currencies = df['currency'].unique().tolist()
    
   
    display_options = available_currencies + ['ALL (TWD Equivalent)']
    default_idx = display_options.index('CAD') if 'CAD' in display_options else 0
    selected_option = st.radio("Current Currency | 目前結算幣別：", display_options, index=default_idx, horizontal=True)
    

    
    is_all_currency = (selected_option == 'ALL (TWD Equivalent)')
    display_currency_symbol = 'TWD' if is_all_currency else selected_option

    if is_all_currency:
        rates_text = " ｜ ".join([f"1 {curr} = {rate} TWD" for curr, rate in EXCHANGE_RATES.items() if curr != 'TWD'])
        st.info(f"💡 **基準匯率 (Reference Rates)：** {rates_text}")
        
    st.markdown("---")

    
    if is_all_currency:
        filtered_df = df.copy()
        def convert_to_twd(row):
            rate = EXCHANGE_RATES.get(row['currency'], 1.0)
            return row['amount_original'] * rate
        
        filtered_df['amount_original'] = filtered_df.apply(convert_to_twd, axis=1)
        filtered_df['currency'] = 'TWD'
        selected_currency = 'TWD_ALL'
    else:
        filtered_df = df[df['currency'] == selected_option].copy()
        selected_currency = selected_option

    # 1. empty state handling
    if 'budgets' not in st.session_state:
        st.session_state.budgets = {}

    # 2. switch case: 
    if selected_currency not in st.session_state.budgets:
        if selected_currency in ['TWD', 'TWD_ALL']:
            st.session_state.budgets[selected_currency] = 30000.0 
        else:
            st.session_state.budgets[selected_currency] = 2000.0  

    # --- Sidebar Setup ---
    with st.sidebar:
        st.header("⚙️ Settings | 設定與除錯")
        st.markdown("### 🎯 Budget Setup | 預算設定")

        db_budget = get_budget_from_db(selected_currency)

        with st.form(key=f'budget_form_{selected_currency}'):
            new_budget = st.number_input(
                f"Set {display_currency_symbol} Budget | 設定本月預算：",
                min_value=0.0,
                value=db_budget,  
                step=100.0
            )

            submit_budget = st.form_submit_button(label="Save | 確定並儲存")

            if submit_budget:
                save_budget_to_db(selected_currency, new_budget)
                st.success(f"✅ {display_currency_symbol} Budget Saved! 預算已儲存！")
                st.rerun()

        monthly_budget = get_budget_from_db(selected_currency)

        st.write("---")

        if st.button("🔄 Refresh Data | 手動更新資料"):
            st.cache_data.clear()
            st.rerun()




           

    # --- 4. Data Board ---
    today = datetime.date.today()
    first_day_of_month = today.replace(day=1)

    # filter to current month based on transaction_date
    filtered_df['transaction_date'] = pd.to_datetime(filtered_df['transaction_date']).dt.date
    monthly_filtered_df = filtered_df[filtered_df['transaction_date'] >= first_day_of_month]

    expense_df = monthly_filtered_df[~monthly_filtered_df['category'].isin(['收入', '轉帳'])]
    income_df = monthly_filtered_df[monthly_filtered_df['category'] == '收入']
    transfer_df = monthly_filtered_df[monthly_filtered_df['category'] == '轉帳']

   

    total_exp = expense_df['amount_original'].sum()
    total_inc = income_df['amount_original'].sum()
    transfer_net = transfer_df['amount_original'].sum()
    net_income = total_inc - total_exp + transfer_net



    col1, col2, col3, col4 = st.columns(4)

    with col1: 
        st.metric(f"Total Expense | 總支出 ({display_currency_symbol})", f"{total_exp:,.2f}", delta_color="inverse")

    with col2:
        st.metric(f"Total Income | 總收入 ({display_currency_symbol})", f"{total_inc:,.2f}")

    with col3:
        st.metric(f"Transfer Flow | 換匯流動 ({display_currency_symbol})", f"{transfer_net:,.2f}", delta_color="normal")

    with col4:
        st.metric(f"Net Cash Flow | 本月淨流向 ({display_currency_symbol})", f"{net_income:,.2f}", delta=f"{net_income:,.2f}")


    st.markdown("---")

    # --- Duplicate Detection with Delete ---
    st.subheader("🔍 Duplicate Transaction Check | 重複交易偵測")


    # initial session state
    if 'pending_delete_ids' not in st.session_state:
        st.session_state.pending_delete_ids = []
    if 'confirm_delete' not in st.session_state:
        st.session_state.confirm_delete = False

    def delete_transactions_by_ids(ids: list):
        if not ids: return False
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                placeholders = ', '.join(['%s'] * len(ids))
                sql = f"DELETE FROM test.daily_expenses WHERE display_id IN ({placeholders})"
                cursor.execute(sql, ids)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            st.error(f"❌ 刪除失敗 Delete failed: {e}")
            return False

    # --- auto scan ---
    all_expense_df = df[~df['category'].isin(['收入', '轉帳', 'Income', 'Transfer'])].copy()

    all_expense_df['currency'] = all_expense_df['currency'].astype(str).str.strip().str.upper()
    all_expense_df['category'] = all_expense_df['category'].astype(str).str.strip()

    display_map = {
        "飲食": "飲食 Food", "Food": "飲食 Food",
        "生活": "生活 Living", "Living": "生活 Living",
        "交通": "交通 Transport", "Transport": "交通 Transport",
        "購物": "購物 Shopping", "Shopping": "購物 Shopping",
        "娛樂": "娛樂 Entertainment", "Entertainment": "娛樂 Entertainment",
        "投資": "投資 Investment", "Investment": "投資 Investment",
        "學習": "學習 Learning", "Learning": "學習 Learning",
    }
    all_expense_df['category'] = all_expense_df['category'].replace(display_map)

    
    all_expense_df['date_str'] = pd.to_datetime(all_expense_df['transaction_date']).dt.strftime('%Y-%m-%d')
    all_expense_df['amount_rounded'] = all_expense_df['amount_original'].abs().round(2)

    
    dup_subset = ['date_str', 'amount_rounded', 'currency']
    dup_mask = all_expense_df.duplicated(subset=dup_subset, keep=False)
    
    dup_df = all_expense_df[dup_mask].sort_values(['date_str', 'amount_rounded', 'display_id'])

    if not dup_df.empty:
        st.warning(f"⚠️ **Detect {len(dup_df)} identical transactions!** Below is the detailed list, the system will keep the latest one (highest ID).")
        
        dup_df_sorted = dup_df.sort_values('display_id', ascending=False)
        to_keep_ids = dup_df_sorted.groupby(dup_subset)['display_id'].first()  
        to_delete_df = dup_df[~dup_df['display_id'].isin(to_keep_ids.values)].copy()
        
        
        display_dup = dup_df.copy()
        display_dup['Status 狀態'] = display_dup['display_id'].apply(
            lambda x: '✅ 保留 Keep' if x in to_keep_ids.values else '🗑️ 待刪除 To Delete'
        )
        display_dup['amount_formatted'] = display_dup['amount_original'].apply(lambda x: f"{x:,.2f}")

        st.dataframe(
            display_dup[['display_id', 'date_str', 'item_description', 'category', 'amount_formatted', 'currency', 'Status 狀態']].rename(columns={
                'display_id': 'ID',
                'date_str': 'Date 日期',
                'item_description': 'Item 品項',
                'category': 'Category 類別',
                'amount_formatted': 'Amount 金額',
                'currency': 'Currency 幣別'
            }).reset_index(drop=True),
            use_container_width=True
        )

        ids_to_delete = to_delete_df['display_id'].tolist()

        # delete button: first step - mark duplicates for deletion
        if not st.session_state.confirm_delete and ids_to_delete:
            if st.button(f"🗑️ Mark and Delete {len(ids_to_delete)} Identical Transactions | Delete {len(ids_to_delete)} Duplicates"):  
                st.session_state.pending_delete_ids = ids_to_delete
                st.session_state.confirm_delete = True
                st.rerun()

        # delete button: second step - confirm deletion
        if st.session_state.confirm_delete:
            st.warning(
                f"⚠️ **確認刪除？ Confirm Delete?**\n\n"
                f" About to delete **{len(st.session_state.pending_delete_ids)} 筆 transaction records**。\n\n"
                f"此操作無法復原，請確認後再按下確認 This operation cannot be undone, please confirm before pressing confirm."
            )
            col_yes, col_no = st.columns([1, 5])
            with col_yes:
                if st.button("✅ 確認刪除 Confirm"):
                    success = delete_transactions_by_ids(st.session_state.pending_delete_ids)
                    if success:
                        st.success(f"✅Successfully deleted {len(st.session_state.pending_delete_ids)} duplicate transactions!")
                        st.session_state.pending_delete_ids = []
                        st.session_state.confirm_delete = False
                        st.cache_data.clear() 
                        st.rerun()
            with col_no:
                if st.button("❌ 取消 Cancel"):
                    st.session_state.pending_delete_ids = []
                    st.session_state.confirm_delete = False
                    st.rerun()

    else:
        st.success("✅ 目前無重複交易紀錄 No duplicate transactions detected.")

    # --- manual query section ---
    with st.expander("🔎 手動查詢特定日期 Manual Duplicate Query"):
        query_date = st.date_input("選擇要查詢的日期 Select a date：", value=datetime.date.today(), key="dup_query_date")
        query_date_str = query_date.strftime('%Y-%m-%d') 

        day_df = all_expense_df[all_expense_df['date_str'] == query_date_str].copy()
        
        if day_df.empty:
            st.info(f"📭 {query_date_str} 當天沒有任何支出紀錄。Not transactions found for this date.")
        else:
            day_dup_mask = day_df.duplicated(subset=dup_subset, keep=False)
            day_dup_df = day_df[day_dup_mask].copy()

            if not day_dup_df.empty:
                st.warning(f"⚠️ {query_date_str} 當天有 **{len(day_dup_df)} 筆**重複交易! Have **{len(day_dup_df)} identical transactions**：")

                day_dup_df['Status 狀態'] = day_dup_df.groupby(dup_subset)['display_id'].transform(
                    lambda x: ['✅ 保留 Keep' if i == x.max() else '🗑️ 待刪除 To Delete' for i in x]
                )
                day_dup_df['amount_formatted'] = day_dup_df['amount_original'].apply(lambda x: f"{x:,.2f}")

                st.dataframe(
                    day_dup_df[['display_id', 'date_str', 'item_description', 'category', 'amount_formatted', 'currency', 'Status 狀態']].rename(columns={
                        'display_id': 'ID',
                        'date_str': 'Date 日期',
                        'item_description': 'Item 品項',
                        'category': 'Category 類別',
                        'amount_formatted': 'Amount 金額',
                        'currency': 'Currency 幣別'
                    }).reset_index(drop=True),
                    use_container_width=True
                )

                manual_ids_to_delete = day_dup_df[day_dup_df['Status 狀態'] == '🗑️ 待刪除 To Delete']['display_id'].tolist()

                if manual_ids_to_delete and st.button(f"🗑️ 刪除此日期的重複交易 {len(manual_ids_to_delete)} 筆 Delete {len(manual_ids_to_delete)} Duplicates!", key="manual_delete_btn"):
                    st.session_state.pending_delete_ids = manual_ids_to_delete
                    st.session_state.confirm_delete = True
                    st.rerun()
            else:
                st.success(f"✅ {query_date_str} 當天無重複交易 No duplicate transactions detected for this date.")




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
                    marker=dict(size=8, color='#F4F1ED', line=dict(width=1, color='#6B655F')) 
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


    # Date Filter
    col_filter, _ = st.columns([1, 1])
    with col_filter:
        today = datetime.date.today()
        first_day_of_month = today.replace(day=1)
        date_range = st.date_input(
            "📅 篩選日期範圍 (Select Date Range)：", 
            value=(first_day_of_month, today)
        )

    if len(date_range) == 2:
        mask = (styled_df['Date 日期'] >= date_range[0]) & (styled_df['Date 日期'] <= date_range[1])
        styled_df = styled_df.loc[mask]
    elif len(date_range) == 1:
        mask = (styled_df['Date 日期'] >= date_range[0])
        styled_df = styled_df.loc[mask]

    
    if not styled_df.empty:
        totals_by_currency = styled_df.groupby('Currency 幣別')['Amount 金額'].sum()
        total_strings = [f"<span style='color: #A0522D; font-size: 1.1em;'>{amt:,.2f} {curr}</span>" for curr, amt in totals_by_currency.items()]
        total_display_text = " ｜ ".join(total_strings)
    else:
        total_display_text = "<span style='color: #A0522D; font-size: 1.1em;'>0.00</span>"

    styled_df['Amount 金額'] = styled_df['Amount 金額'].apply(
        lambda x: f"{x:,.4f}".rstrip('0').rstrip('.') if pd.notnull(x) else "0"
    )

    
    info_col1, info_col2 = st.columns([1, 1])
    with info_col1:
        st.caption(f"Showing {len(styled_df)} records | 共顯示 {len(styled_df)} 筆紀錄")
    with info_col2:
        st.markdown(
            f"<div style='text-align: right;'>"
            f"<b>💰 區間總計 (Total)：{total_display_text}</b>"
            f"</div>", 
            unsafe_allow_html=True
        )

    
    
    

    st.table(styled_df.style.pipe(apply_morandi_table_style).hide(axis="index"))






   
    # --- 7. All Transaction History ---
    with st.expander("🗂️ 查看所有月份紀錄 View All History"):

        summary_df = df.copy()
        summary_df['transaction_date'] = pd.to_datetime(summary_df['transaction_date'])
        summary_df['year_month'] = summary_df['transaction_date'].dt.to_period('M')
        summary_df['amount_original'] = pd.to_numeric(summary_df['amount_original'], errors='coerce').fillna(0)

       
        summary_df['amount_twd'] = summary_df.apply(
            lambda row: row['amount_original'] * EXCHANGE_RATES.get(row['currency'], 1.0), axis=1
        )

        # TWD summary by month and category
        monthly_exp = summary_df[~summary_df['category'].isin(['收入', '轉帳'])].groupby('year_month')['amount_twd'].sum().rename('總支出_TWD')
        monthly_inc = summary_df[summary_df['category'] == '收入'].groupby('year_month')['amount_twd'].sum().rename('總收入_TWD')
        monthly_tra = summary_df[summary_df['category'] == '轉帳'].groupby('year_month')['amount_twd'].sum().rename('換匯流動_TWD')

        # each currency's net flow by month (income - expense + transfer)
        currency_series_list = []
        currency_col_names = []
        for curr in EXCHANGE_RATES.keys():
            curr_df = summary_df[summary_df['currency'] == curr]
            if curr_df['amount_original'].abs().sum() == 0:
                continue
            exp = curr_df[~curr_df['category'].isin(['收入', '轉帳'])].groupby('year_month')['amount_original'].sum()
            inc = curr_df[curr_df['category'] == '收入'].groupby('year_month')['amount_original'].sum()
            tra = curr_df[curr_df['category'] == '轉帳'].groupby('year_month')['amount_original'].sum()
            net = inc.subtract(exp, fill_value=0).add(tra, fill_value=0)
            if net.abs().sum() > 0:
                currency_series_list.append(net)
                currency_col_names.append(f'Net {curr}')

        
        base = pd.concat([monthly_exp, monthly_inc, monthly_tra], axis=1).fillna(0)
        base.columns = ['Total Expense 總支出_TWD', 'Total Income 總收入_TWD', 'Transfer 換匯流動_TWD']
        base['Net Flow 月淨流向_TWD'] = base['Total Income 總收入_TWD'] - base['Total Expense 總支出_TWD'] + base['Transfer 換匯流動_TWD']

        for i, s in enumerate(currency_series_list):
            base[currency_col_names[i]] = s

        monthly_summary = base.fillna(0).sort_index(ascending=False).reset_index()
        monthly_summary['year_month'] = monthly_summary['year_month'].astype(str)

        monthly_summary.rename(columns={
            'year_month': 'Month 月份',
            '總支出_TWD': 'Total Expense 總支出 (TWD)',
            '總收入_TWD': 'Total Income 總收入 (TWD)',
            '換匯流動_TWD': 'Transfer 換匯流動 (TWD)',
            '月淨流向_TWD': 'Net Flow 月淨流向 (TWD)',
        }, inplace=True)

        
        for col in monthly_summary.columns:
            if col == 'Month 月份':
                continue
            vals = monthly_summary[col]
            if isinstance(vals, pd.DataFrame):
                monthly_summary[col] = vals.iloc[:, 0]
            monthly_summary[col] = pd.to_numeric(monthly_summary[col], errors='coerce').fillna(0)
            if 'TWD' in col:
                monthly_summary[col] = monthly_summary[col].apply(lambda x: f"{x:,.0f}")
            else:
                monthly_summary[col] = monthly_summary[col].apply(lambda x: f"{x:,.2f}")

        

        st.caption(f"共 {len(monthly_summary)} 個月份紀錄 | {len(monthly_summary)} months　　💡 Net XXX 欄位為各幣別收入減支出加換匯的原幣淨值，TWD 欄位為換算後總計")
        st.caption(f"共 {len(monthly_summary)} 個月份紀錄 | {len(monthly_summary)} months　　💡 Net XXX means the net flow of each currency by month (income - expense + transfer)")
        st.table(monthly_summary.style.pipe(apply_morandi_table_style).hide(axis="index"))



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

    
    styled_df['Amount 金額'] = pd.to_numeric(styled_df['Amount 金額'], errors='coerce').fillna(0)

    
    styled_df['Date 日期'] = pd.to_datetime(styled_df['Date 日期']).dt.date



    


else:
    st.info("👋 歡迎！目前資料庫是空的。請在 LINE 機器人輸入第一筆帳務（例如：今天晚餐 20 加幣）後重新整理此頁面。")
    st.info("👀 Welcome! The database is currently empty. Please input your first transaction through the LINE bot (e.g., 'Spent 20 Canadian Dollars for dinner today') and refresh this page.")




