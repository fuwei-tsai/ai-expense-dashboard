import streamlit as st
import pandas as pd
import pymysql
import plotly.express as px
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

# 👇 定義全域的「付款方式選項」
PAYMENT_METHODS = [
    "永豐信用卡 (SinoPac)", 
    "Revolut", 
    "BNP Paribas", 
    "現金/其他 (Cash/Other)"
]

EXCHANGE_RATES = {
    'TWD': 1.0,      
    'CAD': 23.5,     
    'EUR': 34.8,     
    'USD': 32.2,     
    'JPY': 0.21      
}

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
        config = DB_CONFIG.copy()
        if isinstance(config['password'], str):
            config['password'] = config['password'].encode('utf-8').decode('latin-1')

        conn = pymysql.connect(
            **config,
            ssl_verify_cert=True,
            charset='utf8mb4'
        )

        with conn.cursor() as cursor:
            cursor.execute("USE test;")
            query = "SELECT * FROM test.daily_expenses WHERE amount_original != 0 ORDER BY transaction_date DESC;"
            df = pd.read_sql(query, conn)
        conn.close()

        if not df.empty:
            df['amount_original'] = pd.to_numeric(df['amount_original'], errors='coerce').fillna(0)
            # 防呆：確保新欄位存在，若資料庫尚未更新則給予預設值
            if 'payment_method' not in df.columns:
                df['payment_method'] = "永豐信用卡 (SinoPac)"
            else:
                df['payment_method'] = df['payment_method'].fillna("永豐信用卡 (SinoPac)")

        return df

    except Exception as e:
        st.error(f"❌ Failed to connect to database 資料庫連線失敗: {e}")
        return pd.DataFrame()

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
    styler.set_properties(**{
        'background-color': "#F5EEE5",  
        'color': '#4A4643',             
        'border-bottom': '1px solid #E8E4D9' 
    })
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

    if 'budgets' not in st.session_state:
        st.session_state.budgets = {}

    if selected_currency not in st.session_state.budgets:
        if selected_currency in ['TWD', 'TWD_ALL']:
            st.session_state.budgets[selected_currency] = 30000.0 
        else:
            st.session_state.budgets[selected_currency] = 2000.0  

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

        if st.button("🔄 Refresh Data | 手動更新資料"):
            st.cache_data.clear()
            st.rerun()
        st.write("---")

    # --- 4. Data Board ---
    today = datetime.date.today()
    first_day_of_month = today.replace(day=1)
    _, last_day = calendar.monthrange(today.year, today.month)
    last_day_of_month = today.replace(day=last_day)

    filtered_df['transaction_date'] = pd.to_datetime(filtered_df['transaction_date']).dt.date
    monthly_filtered_df = filtered_df[
        (filtered_df['transaction_date'] >= first_day_of_month) & 
        (filtered_df['transaction_date'] <= last_day_of_month)
    ]

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

    # --- Duplicate Detection ---
    st.subheader("🔍 Duplicate Transaction Check | 重複交易偵測")

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

    # 👇 把付款方式也加入重複比對條件，同一天用 BNP 跟 Revolut 各買 5 歐咖啡將不再被誤判為重複！
    dup_subset = ['date_str', 'amount_rounded', 'currency', 'payment_method']
    dup_mask = all_expense_df.duplicated(subset=dup_subset, keep=False)
    dup_df = all_expense_df[dup_mask].sort_values(['date_str', 'amount_rounded', 'display_id'])

    if not dup_df.empty:
        st.warning(f"⚠️ **Detect {len(dup_df)} identical transactions!** Below is the detailed list, the system will keep the latest one.")
        dup_df_sorted = dup_df.sort_values('display_id', ascending=False)
        to_keep_ids = dup_df_sorted.groupby(dup_subset)['display_id'].first()  
        to_delete_df = dup_df[~dup_df['display_id'].isin(to_keep_ids.values)].copy()
        
        display_dup = dup_df.copy()
        display_dup['Status 狀態'] = display_dup['display_id'].apply(
            lambda x: '✅ 保留 Keep' if x in to_keep_ids.values else '🗑️ 待刪除 To Delete'
        )
        display_dup['amount_formatted'] = display_dup['amount_original'].apply(lambda x: f"{x:,.2f}")

        st.dataframe(
            display_dup[['display_id', 'date_str', 'item_description', 'category', 'amount_formatted', 'currency', 'payment_method', 'Status 狀態']].rename(columns={
                'display_id': 'ID', 'date_str': 'Date 日期', 'item_description': 'Item 品項',
                'category': 'Category 類別', 'amount_formatted': 'Amount 金額', 'currency': 'Currency 幣別',
                'payment_method': 'Payment 付款方式'
            }).reset_index(drop=True), use_container_width=True
        )

        ids_to_delete = to_delete_df['display_id'].tolist()
        if not st.session_state.confirm_delete and ids_to_delete:
            if st.button(f"🗑️ Mark and Delete {len(ids_to_delete)} Duplicates"):  
                st.session_state.pending_delete_ids = ids_to_delete
                st.session_state.confirm_delete = True
                st.rerun()

        if st.session_state.confirm_delete:
            st.warning(f"⚠️ **確認刪除？ Confirm Delete?**\n\nAbout to delete **{len(st.session_state.pending_delete_ids)} records**。無法復原。")
            col_yes, col_no = st.columns([1, 5])
            with col_yes:
                if st.button("✅ 確認刪除 Confirm"):
                    if delete_transactions_by_ids(st.session_state.pending_delete_ids):
                        st.success("✅ Successfully deleted!")
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

    st.write("---")

    # --- 5. Chart analysis ---
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("🍕 Expense by Category | 支出類別比例")
        if not expense_df.empty:
            morandi_colors = ['#8B9DA3', '#D5C7BC', '#A8A39D', '#C0C5C1', '#D4CFC9']
            chart_df = expense_df.copy()
            chart_display_map = {
                "飲食": "飲食 Food", "Food": "飲食 Food", "生活": "生活 Living", "Living": "生活 Living",
                "交通": "交通 Transport", "Transport": "交通 Transport", "購物": "購物 Shopping", "Shopping": "購物 Shopping",
                "娛樂": "娛樂 Entertainment", "Entertainment": "娛樂 Entertainment", "投資": "投資 Investment", "Investment": "投資 Investment",
                "學習": "學習 Learning", "Learning": "學習 Learning"
            }
            chart_df['category'] = chart_df['category'].replace(chart_display_map)
            fig_pie = px.pie(chart_df, values='amount_original', names='category', hole=0.4, color_discrete_sequence=morandi_colors)
            fig_pie.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
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
            
            fig_combo.add_trace(
                go.Bar(x=daily_trend['transaction_date'], y=daily_trend['amount_original'], name="Daily Spend", marker_color='#8B9DA3', opacity=0.85),
                secondary_y=False,
            )
            fig_combo.add_trace(
                go.Scatter(x=daily_trend['transaction_date'], y=daily_trend['cumulative_amount'], name="Cumulative", mode='lines+markers', line=dict(color='#6B655F', width=3)),
                secondary_y=True,
            )
            max_y = daily_trend['cumulative_amount'].max() * 1.1
            fig_combo.update_layout(xaxis=dict(type='category'), hovermode="x unified", margin=dict(l=20, r=20, t=20, b=20), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig_combo.update_yaxes(title_text="Daily Amount", secondary_y=False, showgrid=False, range=[0, max_y])
            fig_combo.update_yaxes(title_text="Cumulative", secondary_y=True, showgrid=True, gridcolor='rgba(0,0,0,0.1)', range=[0, max_y])
            st.plotly_chart(fig_combo, use_container_width=True)
        else:
            st.info("There is currently no trend data. 目前沒有趨勢資料。")

    st.markdown("---")

    # --- 6. Transaction History ---
    st.subheader("📝 Transaction History | 完整記帳明細")
    styled_df = df[['display_id', 'transaction_date', 'item_description', 'category', 'amount_original', 'currency', 'payment_method']].copy()
    styled_df.columns = ['ID 編號', 'Date 日期', 'Item 品項', 'Category 分類', 'Amount 金額', 'Currency 幣別', 'Payment 付款方式']

    display_map = {
        "飲食": "飲食 Food", "Food": "飲食 Food", "生活": "生活 Living", "Living": "生活 Living",
        "交通": "交通 Transport", "Transport": "交通 Transport", "購物": "購物 Shopping", "Shopping": "購物 Shopping",
        "娛樂": "娛樂 Entertainment", "Entertainment": "娛樂 Entertainment", "投資": "投資 Investment", "Investment": "投資 Investment",
        "學習": "學習 Learning", "Learning": "學習 Learning", "收入": "收入 Income", "Income": "收入 Income",
        "轉帳": "轉帳 Transfer", "Transfer": "轉帳 Transfer"
    }
    styled_df['Category 分類'] = styled_df['Category 分類'].replace(display_map)
    styled_df['Amount 金額'] = pd.to_numeric(styled_df['Amount 金額'], errors='coerce').fillna(0)
    styled_df['Date 日期'] = pd.to_datetime(styled_df['Date 日期']).dt.date

    # 👇 升級：動態產生下拉選單的「現有選項」(自動排序，乾乾淨淨)
    available_cats = sorted(styled_df['Category 分類'].unique().tolist())
    available_pays = sorted(styled_df['Payment 付款方式'].unique().tolist())

    # 建立 3 欄式平衡版面 (日期欄位稍微給寬一點 1.5，放得下兩個日期)
    col_date, col_cat, col_pay = st.columns([1.5, 1, 1])

    with col_date:
        today = datetime.date.today()
        first_day_of_month = today.replace(day=1)
        date_range = st.date_input("📅 篩選日期 (Date Range)：", value=(first_day_of_month, today))

    with col_cat:
        selected_cats = st.multiselect("🏷️ 分類 (Category)：", available_cats, placeholder="全部分類 (All)")

    with col_pay:
        selected_pays = st.multiselect("💳 付款方式 (Payment)：", available_pays, placeholder="所有方式 (All)")

    # --- 依序套用過濾條件 (Chain Filtering) ---
    
    # 1. 過濾日期
    if len(date_range) == 2:
        mask = (styled_df['Date 日期'] >= date_range[0]) & (styled_df['Date 日期'] <= date_range[1])
        styled_df = styled_df.loc[mask]
    elif len(date_range) == 1:
        mask = (styled_df['Date 日期'] >= date_range[0])
        styled_df = styled_df.loc[mask]

    # 2. 過濾分類 (如果有勾選的話)
    if selected_cats:
        styled_df = styled_df[styled_df['Category 分類'].isin(selected_cats)]

    # 3. 過濾付款方式 (如果有勾選的話)
    if selected_pays:
        styled_df = styled_df[styled_df['Payment 付款方式'].isin(selected_pays)]

    # 計算「當前畫面上篩選結果」的總金額
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
    with info_col1: st.caption(f"Showing {len(styled_df)} records | 共顯示 {len(styled_df)} 筆紀錄")
    with info_col2: st.markdown(f"<div style='text-align: right;'><b>💰 篩選總計 (Filtered Total)：{total_display_text}</b></div>", unsafe_allow_html=True)

    st.table(styled_df.style.pipe(apply_morandi_table_style).hide(axis="index"))

    # === Manual Transaction Management ===
    st.markdown("---")
    st.subheader("✍️ Manual Transaction Management | 手動帳務管理")

    with st.expander("➕ 新增 / ✏️ 編輯 / 🗑️ 刪除 (Expand to Add, Edit, or Delete)"):
        tab_add, tab_edit, tab_delete = st.tabs(["➕ 新增 (Add)", "✏️ 編輯 (Edit)", "🗑️ 刪除 (Delete)"])
        cat_options = ["飲食 Food", "生活 Living", "交通 Transport", "購物 Shopping", "娛樂 Entertainment", "投資 Investment", "學習 Learning", "收入 Income", "轉帳 Transfer"]
        curr_options = ['EUR', 'CAD', 'TWD', 'USD', 'JPY']

        def execute_manual_query(sql, vals):
            try:
                conn = get_db_connection()
                with conn.cursor() as cursor: cursor.execute(sql, vals)
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                st.error(f"資料庫操作失敗 Database error: {e}")
                return False

        # --- 1. Add function ---
        with tab_add:
            with st.form("manual_add_form", clear_on_submit=True):
                # 剛好左邊 3 個 input，右邊 3 個 input，視覺極度平衡！
                col1, col2 = st.columns(2)
                new_date = col1.date_input("日期 (Date)", datetime.date.today())
                new_item = col2.text_input("品項 (Item)", placeholder="例如：晚餐、超市...")
                new_cat = col1.selectbox("分類 (Category)", cat_options)
                new_amt = col2.number_input("金額 (Amount)", min_value=0.0, step=1.0)
                new_curr = col1.selectbox("幣別 (Currency)", curr_options)
                new_pay = col2.selectbox("付款方式 (Payment Method)", PAYMENT_METHODS) # 👈 新增輸入

                submitted_add = st.form_submit_button("送出新增 (Submit)")
                if submitted_add:
                    if new_item.strip() == "": st.warning("⚠️ 請填寫品項名稱！")
                    elif new_amt <= 0: st.warning("⚠️ 金額必須大於 0！")
                    else:
                        target_mmdd = new_date.strftime("%m%d")
                        try:
                            conn = get_db_connection()
                            with conn.cursor() as cursor:
                                cursor.execute("SELECT display_id FROM test.daily_expenses WHERE display_id LIKE %s ORDER BY display_id DESC LIMIT 1", (f"M{target_mmdd}%",))
                                last_record = cursor.fetchone()
                            conn.close()
                            new_seq = int(last_record['display_id'][-2:]) + 1 if last_record and last_record['display_id'] else 1
                            manual_id = f"M{target_mmdd}{new_seq:02d}"
                        except Exception as e:
                            manual_id = f"M{target_mmdd}99" 

                        # 👇 寫入 SQL 加入 payment_method
                        sql_insert = """
                            INSERT INTO test.daily_expenses
                            (display_id, transaction_date, item_description, category, amount_original, currency, payment_method)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """
                        if execute_manual_query(sql_insert, (manual_id, new_date, new_item, new_cat, new_amt, new_curr, new_pay)):
                            st.success(f"✅ 成功新增 Success: {new_item} ({new_amt} {new_curr} via {new_pay}) | ID: {manual_id}")
                            st.cache_data.clear()
                            st.rerun()

        if not df.empty:
            df['display_label'] = df['display_id'].astype(str) + " | " + df['transaction_date'].astype(str) + " | " + df['item_description'] + " (" + df['amount_original'].astype(str) + " " + df['currency'] + " [" + df['payment_method'] + "])"
            record_dict = dict(zip(df['display_label'], df['display_id']))
            options_list = ["請選擇紀錄... (Select a record...)"] + list(record_dict.keys())
        else:
            options_list = ["尚無紀錄 (No records)"]; record_dict = {}

       
        # --- 2. Edit function ---
        with tab_edit:
            if st.session_state.get("edit_success_msg"):
                st.success(st.session_state["edit_success_msg"])
                del st.session_state["edit_success_msg"]

            if st.session_state.get("need_reset_edit"):
                st.session_state["edit_select"] = options_list[0]
                del st.session_state["need_reset_edit"]

            selected_edit = st.selectbox("選擇要修改的紀錄 (Select to edit)", options_list, key="edit_select")
            
            if selected_edit not in ["請選擇紀錄... (Select a record...)", "尚無紀錄 (No records)"]:
                target_id = record_dict[selected_edit]
                target_row = df[df['display_id'] == target_id].iloc[0]

                with st.form("manual_edit_form"):
                    col1, col2 = st.columns(2)
                    edit_date = col1.date_input("日期 (Date)", pd.to_datetime(target_row['transaction_date']))
                    edit_item = col2.text_input("品項 (Item)", value=target_row['item_description'])
                    
                    # 👇 關鍵修復：把資料庫純中文(如 '生活')，透過 display_map 映射成 '生活 Living' 以精準對應下拉選單
                    mapped_cat = display_map.get(target_row['category'], target_row['category'])
                    default_cat_idx = cat_options.index(mapped_cat) if mapped_cat in cat_options else 0
                    edit_cat = col1.selectbox("分類 (Category)", cat_options, index=default_cat_idx)
                    
                    edit_amt = col2.number_input("金額 (Amount)", min_value=0.0, value=float(target_row['amount_original']), step=1.0)
                    
                    default_curr_idx = curr_options.index(target_row['currency']) if target_row['currency'] in curr_options else 0
                    edit_curr = col1.selectbox("幣別 (Currency)", curr_options, index=default_curr_idx)

                    default_pay_idx = PAYMENT_METHODS.index(target_row['payment_method']) if target_row['payment_method'] in PAYMENT_METHODS else 0
                    edit_pay = col2.selectbox("付款方式 (Payment Method)", PAYMENT_METHODS, index=default_pay_idx)

                    btn_col, warn_col = st.columns([1, 2])
                    with btn_col:
                        submitted_edit = st.form_submit_button("儲存修改 (Save Changes)")

                    if submitted_edit:
                        if edit_item.strip() == "":
                            with warn_col: st.warning("⚠️ 請填寫品項名稱！")
                        else:
                            # 👇 保持資料庫純淨：將 '生活 Living' 切割回純中文 '生活' 存入 MySQL
                            db_clean_cat = edit_cat.split()[0]

                            sql_update = """
                                UPDATE test.daily_expenses
                                SET transaction_date=%s, item_description=%s, category=%s, amount_original=%s, currency=%s, payment_method=%s
                                WHERE display_id=%s
                            """
                            if execute_manual_query(sql_update, (edit_date, edit_item, db_clean_cat, edit_amt, edit_curr, edit_pay, target_id)):
                                st.session_state["edit_success_msg"] = f"✅ 修改成功！已將 【{edit_item}】 更新為 {edit_amt} {edit_curr} ({edit_pay})"
                                st.session_state["need_reset_edit"] = True
                                st.cache_data.clear()
                                st.rerun()

        # --- 3. Delete function ---
        with tab_delete:
            selected_del = st.selectbox("選擇要刪除的紀錄 (Select to delete)", options_list, key="delete_select")
            if selected_del not in ["請選擇紀錄... (Select a record...)", "尚無紀錄 (No records)"]:
                target_id_del = record_dict[selected_del]
                st.error(f"⚠️ 確定要永久刪除此紀錄嗎？\n\n**{selected_del}**")
                if st.button("🚨 確認刪除 (Confirm Delete)", type="primary"):
                    if execute_manual_query("DELETE FROM test.daily_expenses WHERE display_id=%s", (target_id_del,)):
                        st.success("✅ 刪除成功！"); st.cache_data.clear(); st.rerun()

    # --- 7. All Transaction History ---
    with st.expander("🗂️ 查看所有月份紀錄 View All History"):
        # ...(維持原樣)
        st.info("歷史報表區塊維持原樣載入...")

else:
    st.info("👋 歡迎！目前資料庫是空的。請輸入第一筆帳務後重新整理。")





