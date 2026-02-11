# -*- coding: utf-8 -*-
"""
缠论选股系统 - Streamlit Web App
支持自定义股票池 + 板块自动扫描
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import io
import base64
from datetime import datetime, timedelta
import tushare as ts
from pypinyin import lazy_pinyin, Style
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image, ImageDraw, ImageFont

# ========== 数据持久化 ==========
DATA_DIR = ".streamlit_data"
os.makedirs(DATA_DIR, exist_ok=True)

WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")
HISTORY_FILE = os.path.join(DATA_DIR, "analysis_history.json")

def load_watchlist():
    """加载自选股票"""
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_watchlist(watchlist):
    """保存自选股票"""
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)

def add_to_watchlist(code, name):
    """添加股票到自选"""
    watchlist = load_watchlist()
    if not any(w['code'] == code for w in watchlist):
        watchlist.append({
            'code': code,
            'name': name,
            'added_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        })
        save_watchlist(watchlist)
        return True
    return False

def remove_from_watchlist(code):
    """从自选移除股票"""
    watchlist = load_watchlist()
    watchlist = [w for w in watchlist if w['code'] != code]
    save_watchlist(watchlist)

def save_analysis_history(results):
    """保存分析历史"""
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    
    # 添加本次分析
    history.append({
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'results': results
    })
    
    # 只保留最近20次分析
    history = history[-20:]
    
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_analysis_history():
    """加载分析历史"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# ========== 生成结果图片 ==========

def generate_result_image(results):
    """生成分析结果图片 - 优化手机浏览"""
    if not results:
        return None
    
    # 筛选有信号的股票
    buy3 = [r for r in results if r['signal'] == '三买']
    buy1 = [r for r in results if r['signal'] == '一买']
    
    # 如果没有信号股票，不生成图片
    if not buy3 and not buy1:
        return None
    
    # 设置中文字体 - 尝试多种字体
    import matplotlib
    matplotlib.rcParams['font.sans-serif'] = [
        'SimHei', 'DejaVu Sans', 'Arial Unicode MS', 
        'WenQuanYi Micro Hei', 'Noto Sans CJK SC'
    ]
    matplotlib.rcParams['axes.unicode_minus'] = False
    
    # 计算图片高度 - 紧凑布局
    signal_count = len(buy3) + len(buy1)
    fig_height = 3 + signal_count * 0.6  # 紧凑行距
    
    # 创建图片 - 适合手机宽度
    fig, ax = plt.subplots(figsize=(8, fig_height))
    ax.axis('off')
    
    # 颜色定义
    color_title = '#1f77b4'
    color_green = '#2ecc71'
    color_orange = '#f39c12'
    color_gray = '#7f8c8d'
    color_dark = '#2c3e50'
    
    # 标题
    fig.text(0.5, 0.98, '缠论选股分析结果', ha='center', va='top', 
             fontsize=16, fontweight='bold', color=color_title)
    fig.text(0.5, 0.95, datetime.now().strftime('%Y-%m-%d %H:%M'), 
             ha='center', va='top', fontsize=9, color=color_gray)
    
    # 统计信息 - 紧凑排列
    y_pos = 0.92
    stats_text = f'分析:{len(results)}只 | 三买:{len(buy3)}只 | 一买:{len(buy1)}只'
    fig.text(0.5, y_pos, stats_text, ha='center', va='top', 
             fontsize=10, color=color_dark)
    
    y_pos -= 0.06
    
    # 三买股票
    if buy3:
        fig.text(0.05, y_pos, '【三买信号-强势突破】', fontsize=11, 
                fontweight='bold', color=color_green)
        y_pos -= 0.04
        
        for r in buy3:
            # 股票信息 - 单行紧凑显示
            line1 = f"{r['code']} {r['name']}  ¥{r['price']:.2f} ({r['change']:+.1f}%)"
            fig.text(0.05, y_pos, line1, fontsize=10, fontweight='bold', color=color_dark)
            y_pos -= 0.025
            
            # 买卖点 - 简化显示
            stop_str = f"¥{r.get('stop_loss', 0):.1f}({r.get('stop_loss_pct', 0):+.0f}%)" if r.get('stop_loss') else "-"
            target_str = f"¥{r.get('target_price', 0):.1f}(+{r.get('target_pct', 0):.0f}%)" if r.get('target_price') else "-"
            line2 = f"    买入:¥{r['price']:.1f} → 止损:{stop_str} → 目标:{target_str}"
            fig.text(0.05, y_pos, line2, fontsize=8, color=color_gray)
            y_pos -= 0.03
    
    # 一买股票
    if buy1:
        y_pos -= 0.01
        fig.text(0.05, y_pos, '【一买信号-底部反转】', fontsize=11, 
                fontweight='bold', color=color_orange)
        y_pos -= 0.04
        
        for r in buy1:
            # 股票信息
            line1 = f"{r['code']} {r['name']}  ¥{r['price']:.2f} ({r['change']:+.1f}%)"
            fig.text(0.05, y_pos, line1, fontsize=10, fontweight='bold', color=color_dark)
            y_pos -= 0.025
            
            # 买卖点
            stop_str = f"¥{r.get('stop_loss', 0):.1f}({r.get('stop_loss_pct', 0):+.0f}%)" if r.get('stop_loss') else "-"
            target_str = f"¥{r.get('target_price', 0):.1f}(+{r.get('target_pct', 0):.0f}%)" if r.get('target_price') else "-"
            line2 = f"    买入:¥{r['price']:.1f} → 止损:{stop_str} → 目标:{target_str}"
            fig.text(0.05, y_pos, line2, fontsize=8, color=color_gray)
            y_pos -= 0.03
    
    # 风险提示
    y_pos -= 0.02
    fig.text(0.5, max(y_pos, 0.02), 
             '风险提示:以上分析仅供参考，不构成投资建议。', 
             ha='center', fontsize=7, color='#e74c3c', style='italic')
    
    # 保存为图片 - 高DPI保证清晰度
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', 
                facecolor='white', edgecolor='none', pad_inches=0.1)
    buf.seek(0)
    plt.close()
    
    return buf

# ========== 页面配置 ==========
st.set_page_config(
    page_title="缠论选股系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== Tushare初始化 ==========
# 从环境变量读取Token（部署到云端时设置）
TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN', '')

if not TUSHARE_TOKEN:
    st.error("⚠️ 未设置TUSHARE_TOKEN环境变量！请在Streamlit Cloud设置中添加。")
    st.stop()

pro = ts.pro_api(TUSHARE_TOKEN)

# ========== 股票列表缓存 ==========
@st.cache_data(ttl=3600)  # 缓存1小时
def get_all_stocks():
    """获取全市场股票列表，用于搜索联想"""
    try:
        df = pro.stock_basic(exchange='', list_status='L', 
                            fields='ts_code,symbol,name,area,industry')
        if df is not None and not df.empty:
            # 添加拼音首字母
            df['pinyin'] = df['name'].apply(lambda x: ''.join(lazy_pinyin(x, style=Style.FIRST_LETTER)).upper())
            df['pinyin_full'] = df['name'].apply(lambda x: ''.join(lazy_pinyin(x)).lower())
            return df
    except:
        pass
    return None

def search_stocks(query, stock_df, limit=20):
    """搜索股票：支持代码、中文名称、拼音首字母"""
    if not query or stock_df is None:
        return []
    
    query = query.strip().upper()
    
    # 1. 代码搜索（精确匹配开头）
    code_match = stock_df[stock_df['symbol'].str.startswith(query, na=False)]
    
    # 2. 中文名称搜索（包含）
    name_match = stock_df[stock_df['name'].str.contains(query, na=False, case=False)]
    
    # 3. 拼音首字母搜索
    pinyin_match = stock_df[stock_df['pinyin'].str.startswith(query, na=False)]
    
    # 4. 全拼搜索
    pinyin_full_match = stock_df[stock_df['pinyin_full'].str.contains(query.lower(), na=False)]
    
    # 合并结果并去重
    result = pd.concat([code_match, name_match, pinyin_match, pinyin_full_match]).drop_duplicates()
    
    # 返回前limit个
    return result.head(limit).to_dict('records')

# 获取股票列表
stock_df = get_all_stocks()

# ========== CSS样式 ==========
st.markdown("""
<style>
.main {
    padding: 0rem 1rem;
}
.metric-card {
    background-color: #f0f2f6;
    padding: 1rem;
    border-radius: 0.5rem;
    margin: 0.5rem 0;
}
.stock-card {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.buy-signal {
    background-color: #e8f5e9;
    border-left: 4px solid #4caf50;
}
.buy-1 {
    background-color: #fff3e0;
    border-left: 4px solid #ff9800;
}
</style>
""", unsafe_allow_html=True)

# ========== 缠论核心算法 ==========

def handle_inclusion(df):
    """K线包含处理"""
    if df.empty:
        return df
    
    df = df.copy()
    df.columns = [str(col).lower() for col in df.columns]
    processed_candles = []
    i = 0
    
    while i < len(df):
        current_candle = df.iloc[i].copy()
        j = i + 1
        
        while j < len(df):
            next_candle = df.iloc[j]
            is_included = (next_candle['high'] >= current_candle['high'] and 
                          next_candle['low'] <= current_candle['low'])
            is_including = (next_candle['high'] <= current_candle['high'] and 
                           next_candle['low'] >= current_candle['low'])
            
            if is_included or is_including:
                current_candle['high'] = max(current_candle['high'], next_candle['high'])
                current_candle['low'] = min(current_candle['low'], next_candle['low'])
                current_candle['open'] = next_candle['open']
                current_candle['close'] = next_candle['close']
                j += 1
            else:
                break
        
        processed_candles.append(current_candle)
        i = j
    
    return pd.DataFrame(processed_candles)

def is_top_fractal(df, idx):
    """顶分型判断"""
    if idx < 2 or idx >= len(df):
        return False
    p2 = df.iloc[idx-1]
    p1 = df.iloc[idx-2]
    p3 = df.iloc[idx]
    return (p2['high'] > p1['high'] and p2['high'] > p3['high'] and 
            p2['low'] > p1['low'] and p2['low'] > p3['low'])

def is_bottom_fractal(df, idx):
    """底分型判断"""
    if idx < 2 or idx >= len(df):
        return False
    p2 = df.iloc[idx-1]
    p1 = df.iloc[idx-2]
    p3 = df.iloc[idx]
    return (p2['low'] < p1['low'] and p2['low'] < p3['low'] and 
            p2['high'] < p1['high'] and p2['high'] < p3['high'])

def find_strokes(df):
    """寻找缠论笔"""
    if df.empty or len(df) < 5:
        return [], 0, 0
    
    strokes = []
    fractals = []
    ding_count = 0
    di_count = 0
    
    for i in range(2, len(df)):
        if is_top_fractal(df, i):
            fractals.append({'idx': i-1, 'type': 'top', 'price': df.iloc[i-1]['high']})
            ding_count += 1
        elif is_bottom_fractal(df, i):
            fractals.append({'idx': i-1, 'type': 'bottom', 'price': df.iloc[i-1]['low']})
            di_count += 1
    
    if len(fractals) < 2:
        return strokes, ding_count, di_count
    
    current_stroke_start = None
    for i in range(len(fractals)):
        current_fractal = fractals[i]
        if current_stroke_start is None:
            current_stroke_start = current_fractal
        else:
            if current_fractal['type'] != current_stroke_start['type']:
                if current_fractal['idx'] - current_stroke_start['idx'] >= 2:
                    if (current_stroke_start['type'] == 'bottom' and 
                        current_fractal['type'] == 'top' and 
                        current_fractal['price'] > current_stroke_start['price']):
                        strokes.append({'type': 'up', 'start': current_stroke_start['price'], 'end': current_fractal['price']})
                        current_stroke_start = current_fractal
                    elif (current_stroke_start['type'] == 'top' and 
                          current_fractal['type'] == 'bottom' and 
                          current_fractal['price'] < current_stroke_start['price']):
                        strokes.append({'type': 'down', 'start': current_stroke_start['price'], 'end': current_fractal['price']})
                        current_stroke_start = current_fractal
                    else:
                        current_stroke_start = current_fractal
                else:
                    current_stroke_start = current_fractal
            else:
                if ((current_fractal['type'] == 'top' and current_fractal['price'] > current_stroke_start['price']) or
                    (current_fractal['type'] == 'bottom' and current_fractal['price'] < current_stroke_start['price'])):
                    current_stroke_start = current_fractal
    
    return strokes, ding_count, di_count

def calculate_zhongshu(df):
    """计算中枢"""
    df['mid'] = (df['high'] + df['low']) / 2
    return {
        'low': df['mid'].quantile(0.40),
        'high': df['mid'].quantile(0.60),
    }

def analyze_stock(symbol, name, days=90):
    """分析单只股票"""
    try:
        # 获取数据
        if symbol.startswith('6'):
            ts_code = f"{symbol}.SH"
        else:
            ts_code = f"{symbol}.SZ"
        
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days*2)).strftime('%Y%m%d')
        df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is None or len(df) < 20:
            return None
        
        df = df.sort_values('trade_date').reset_index(drop=True)
        df = df.rename(columns={
            'trade_date': 'date', 'open': 'open', 'close': 'close',
            'high': 'high', 'low': 'low', 'vol': 'volume', 'pct_chg': 'pct_chg'
        })
        df = df.tail(days)
        
        # 计算指标
        current_price = df.iloc[-1]['close']
        current_chg = df.iloc[-1]['pct_chg']
        max_price = df['high'].max()
        min_price = df['low'].min()
        
        # 缠论分析
        df_processed = handle_inclusion(df.reset_index(drop=True))
        strokes, ding_count, di_count = find_strokes(df_processed)
        zhongshu = calculate_zhongshu(df)
        
        # 判断信号并生成买卖建议
        signal = "无"
        action = "观望"
        entry_price = None
        stop_loss = None
        target_price = None
        stop_loss_pct = None
        target_pct = None
        risk_level = "中"
        suggestion = ""
        
        if current_price > zhongshu['high'] and strokes:
            recent_up = [s for s in strokes if s['type'] == 'up']
            if recent_up and recent_up[-1]['end'] > zhongshu['high']:
                signal = "三买"
                action = "买入"
                
                # 买入建议
                entry_price = current_price
                # 止损：中枢上沿下方2%或-5%取较大值
                stop_loss = max(zhongshu['high'] * 0.98, current_price * 0.95)
                stop_loss_pct = (stop_loss - current_price) / current_price * 100
                
                # 目标：前期高点
                target_price = max_price
                target_pct = (target_price - current_price) / current_price * 100
                
                # 风险等级
                if target_pct < 3:
                    risk_level = "高"
                    suggestion = "突破但空间有限，谨慎追涨"
                elif target_pct < 8:
                    risk_level = "中"
                    suggestion = "突破有效，可适量参与"
                else:
                    risk_level = "中"
                    suggestion = "强势突破，空间充足"
                
        elif current_price < zhongshu['low'] and strokes:
            recent_down = [s for s in strokes if s['type'] == 'down']
            if recent_down:
                recent_low = recent_down[-1]['end']
                rebound_pct = (current_price - recent_low) / recent_low * 100
                if rebound_pct > 1:
                    signal = "一买"
                    action = "关注"
                    
                    # 买入建议
                    entry_price = current_price
                    # 止损：前低下方3%
                    stop_loss = recent_low * 0.97
                    stop_loss_pct = (stop_loss - current_price) / current_price * 100
                    
                    # 目标：中枢下沿
                    target_price = zhongshu['low']
                    target_pct = (target_price - current_price) / current_price * 100
                    
                    risk_level = "高"
                    if target_pct < 3:
                        suggestion = "反弹空间有限，建议观望"
                    else:
                        suggestion = "超跌反弹，小仓位试水"
        
        return {
            'code': symbol, 'name': name, 'price': current_price, 'change': current_chg,
            'max_price': max_price, 'min_price': min_price,
            'ding_count': ding_count, 'di_count': di_count, 'stroke_count': len(strokes),
            'zhongshu_low': zhongshu['low'], 'zhongshu_high': zhongshu['high'],
            'signal': signal, 'action': action,
            'entry_price': entry_price, 'stop_loss': stop_loss, 'target_price': target_price,
            'stop_loss_pct': stop_loss_pct, 'target_pct': target_pct,
            'risk_level': risk_level, 'suggestion': suggestion
        }
    except Exception as e:
        return None

def get_concept_stocks(concept_name):
    """获取板块成分股"""
    try:
        concepts = pro.concept()
        matched = concepts[concepts['name'].str.contains(concept_name, na=False, case=False)]
        
        if matched.empty:
            return None
        
        concept_code = matched.iloc[0]['code']
        detail = pro.concept_detail(id=concept_code, fields='ts_code,name')
        
        if detail is None or detail.empty:
            return None
        
        stock_list = []
        for _, row in detail.iterrows():
            symbol = row['ts_code'].split('.')[0]
            stock_list.append((symbol, row['name']))
        
        return stock_list
    except:
        return None

# ========== 页面主逻辑 ==========

def main():
    # 标题
    st.title("📈 缠论选股系统 v3.0")
    st.markdown("**智能缠论分析 | 自定义股票池 | 板块自动扫描**")
    
    # 侧边栏配置
    st.sidebar.header("⚙️ 分析配置")
    
    # 股票池选择方式
    pool_mode = st.sidebar.radio(
        "股票池选择方式",
        ["自定义股票池", "板块自动扫描"],
        help="选择自定义股票池手动输入股票，或选择板块自动获取成分股"
    )
    
    stock_list = []
    
    if pool_mode == "自定义股票池":
        st.sidebar.markdown("---")
        st.sidebar.subheader("📝 自定义股票池")
        
        # 初始化session_state
        if 'selected_stocks' not in st.session_state:
            st.session_state['selected_stocks'] = []
        
        # 股票搜索框
        search_query = st.sidebar.text_input(
            "🔍 搜索股票（代码/名称/拼音）",
            placeholder="输入：000001 或 平安 或 PA",
            help="支持：股票代码、中文名称、拼音首字母（如PA=平安）"
        )
        
        # 显示搜索结果
        if search_query and stock_df is not None:
            search_results = search_stocks(search_query, stock_df, limit=10)
            if search_results:
                st.sidebar.markdown("**搜索结果：**")
                for stock in search_results:
                    col1, col2 = st.sidebar.columns([3, 1])
                    col1.markdown(f"**{stock['symbol']}** {stock['name']}")
                    if col2.button("➕ 添加", key=f"add_{stock['symbol']}"):
                        if stock['symbol'] not in [s[0] for s in st.session_state['selected_stocks']]:
                            st.session_state['selected_stocks'].append((stock['symbol'], stock['name']))
                            st.rerun()
        
        # 显示已选股票
        if st.session_state['selected_stocks']:
            st.sidebar.markdown("---")
            st.sidebar.markdown(f"**已选股票 ({len(st.session_state['selected_stocks'])})：**")
            for i, (code, name) in enumerate(st.session_state['selected_stocks']):
                cols = st.sidebar.columns([4, 1])
                cols[0].markdown(f"{code} {name}")
                if cols[1].button("❌", key=f"del_{code}"):
                    st.session_state['selected_stocks'].pop(i)
                    st.rerun()
            
            if st.sidebar.button("🗑️ 清空全部"):
                st.session_state['selected_stocks'] = []
                st.rerun()
        
        stock_list = st.session_state['selected_stocks']
        
    else:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔍 板块自动扫描")
        
        # 常用概念列表
        common_concepts = ["光纤", "芯片", "人工智能", "新能源", "半导体", "军工", "医药", "白酒", "银行", "证券"]
        concept_name = st.sidebar.selectbox("选择概念板块", common_concepts)
        
        if st.sidebar.button("🔄 获取成分股"):
            with st.spinner(f"正在获取 {concept_name} 板块成分股..."):
                concept_stocks = get_concept_stocks(concept_name)
                if concept_stocks:
                    st.session_state['concept_stocks'] = concept_stocks
                    st.sidebar.success(f"获取到 {len(concept_stocks)} 只成分股")
                else:
                    st.sidebar.error("未找到该板块成分股")
        
        if 'concept_stocks' in st.session_state:
            stock_list = st.session_state['concept_stocks']
            st.sidebar.info(f"当前板块: {len(stock_list)} 只股票")
    
    # 分析参数
    st.sidebar.markdown("---")
    days = st.sidebar.slider("分析天数", 30, 180, 90)
    
    # 开始分析
    st.sidebar.markdown("---")
    if st.sidebar.button("🚀 开始分析", type="primary", use_container_width=True):
        if not stock_list:
            st.error("请先添加股票或选择板块！")
            return
        
        # 分析进度
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        for i, (symbol, name) in enumerate(stock_list):
            progress = (i + 1) / len(stock_list)
            progress_bar.progress(progress)
            status_text.text(f"分析中... {symbol} {name} ({i+1}/{len(stock_list)})")
            
            result = analyze_stock(symbol, name, days)
            if result:
                results.append(result)
        
        progress_bar.empty()
        status_text.empty()
        
        # 保存结果
        st.session_state['results'] = results
        
        # 保存分析历史
        save_analysis_history(results)
    
    # 侧边栏：我的自选和历史
    st.sidebar.markdown("---")
    st.sidebar.subheader("⭐ 我的自选")
    
    watchlist = load_watchlist()
    if watchlist:
        st.sidebar.markdown(f"自选股票 ({len(watchlist)}只)：")
        for item in watchlist:
            cols = st.sidebar.columns([3, 1])
            cols[0].markdown(f"{item['code']} {item['name']}")
            if cols[1].button("🗑️", key=f"watch_del_{item['code']}"):
                remove_from_watchlist(item['code'])
                st.rerun()
        
        if st.sidebar.button("📊 分析全部自选"):
            st.session_state['selected_stocks'] = [(w['code'], w['name']) for w in watchlist]
            st.rerun()
    else:
        st.sidebar.info("暂无自选股票")
    
    # 分析历史
    st.sidebar.markdown("---")
    st.sidebar.subheader("📜 分析历史")
    
    history = load_analysis_history()
    if history:
        # 显示最近5次分析
        for i, record in enumerate(reversed(history[-5:])):
            ts = record['timestamp']
            count = len(record.get('results', []))
            if st.sidebar.button(f"📅 {ts} ({count}只)", key=f"hist_{i}"):
                st.session_state['results'] = record['results']
                st.rerun()
    else:
        st.sidebar.info("暂无分析历史")
    
    # 显示结果
    if 'results' in st.session_state:
        results = st.session_state['results']
        
        # 统计
        col1, col2, col3, col4 = st.columns(4)
        buy3 = [r for r in results if r['signal'] == '三买']
        buy1 = [r for r in results if r['signal'] == '一买']
        
        col1.metric("📊 分析股票", len(results))
        col2.metric("🚀 三买信号", len(buy3), delta="强势突破")
        col3.metric("📉 一买信号", len(buy1), delta="底部反转")
        col4.metric("❌ 无信号", len(results) - len(buy3) - len(buy1))
        
        st.markdown("---")
        
        # 三买信号股票
        if buy3:
            st.subheader("🎯 三买信号")
            for r in buy3:
                # 紧凑卡片布局
                with st.container():
                    # 第一行：股票信息 + 信号标签（紧凑排列）
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.success("买入", icon="🚀")
                    
                    # 第二行：买卖点（紧凑2x2网格）
                    c1, c2 = st.columns(2)
                    with c1:
                        st.caption(f"💰 买入: ¥{r['price']:.2f}")
                    with c2:
                        if r.get('target_price'):
                            st.caption(f"🎯 目标: ¥{r['target_price']:.1f} (+{r['target_pct']:.0f}%)")
                    
                    c3, c4 = st.columns(2)
                    with c3:
                        if r.get('stop_loss'):
                            st.caption(f"🛑 止损: ¥{r['stop_loss']:.1f} ({r['stop_loss_pct']:+.0f}%)")
                    with c4:
                        watchlist = load_watchlist()
                        if any(w['code'] == r['code'] for w in watchlist):
                            st.caption("✅ 已自选")
                        else:
                            if st.button("⭐ 自选", key=f"w_{r['code']}"):
                                add_to_watchlist(r['code'], r['name'])
                                st.rerun()
                    
                    st.divider()
        
        # 一买信号股票
        if buy1:
            st.subheader("📉 一买信号")
            for r in buy1:
                with st.container():
                    # 第一行
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.warning("关注", icon="📉")
                    
                    # 第二行
                    c1, c2 = st.columns(2)
                    with c1:
                        st.caption(f"💰 买入: ¥{r['price']:.2f}")
                    with c2:
                        if r.get('target_price'):
                            st.caption(f"🎯 目标: ¥{r['target_price']:.1f} (+{r['target_pct']:.0f}%)")
                    
                    c3, c4 = st.columns(2)
                    with c3:
                        if r.get('stop_loss'):
                            st.caption(f"🛑 止损: ¥{r['stop_loss']:.1f} ({r['stop_loss_pct']:.0f}%)")
                    with c4:
                        watchlist = load_watchlist()
                        if any(w['code'] == r['code'] for w in watchlist):
                            st.caption("✅ 已自选")
                        else:
                            if st.button("⭐ 自选", key=f"w_{r['code']}"):
                                add_to_watchlist(r['code'], r['name'])
                                st.rerun()
                    
                    st.divider()
        
        # 完整数据表
        st.markdown("---")
        st.subheader("📋 完整分析数据")
        
        # 安全地创建DataFrame
        try:
            df_results = pd.DataFrame(results)
            
            # 确保所有需要的列都存在
            required_cols = ['code', 'name', 'price', 'change', 'signal', 'stroke_count', 'ding_count', 'di_count', 'min_price', 'max_price']
            for col in required_cols:
                if col not in df_results.columns:
                    df_results[col] = ''
            
            # 创建区间列
            df_results['区间'] = df_results.apply(
                lambda x: f"{x.get('min_price', 0):.1f}-{x.get('max_price', 0):.1f}" if pd.notna(x.get('min_price')) and pd.notna(x.get('max_price')) else '-', 
                axis=1
            )
            
            # 选择显示的列
            display_cols = ['code', 'name', 'price', 'change', 'signal', 'stroke_count', 'ding_count', 'di_count', '区间']
            df_display = df_results[[col for col in display_cols if col in df_results.columns]].copy()
            
            # 重命名列
            column_names = {
                'code': '代码',
                'name': '名称', 
                'price': '价格',
                'change': '涨跌%',
                'signal': '信号',
                'stroke_count': '笔数',
                'ding_count': '顶分型',
                'di_count': '底分型',
                '区间': '区间'
            }
            df_display = df_display.rename(columns=column_names)
            
            st.dataframe(df_display, use_container_width=True, height=400)
            
            # 导出按钮区域
            export_cols = st.columns(2)
            
            with export_cols[0]:
                # 导出CSV
                csv = df_display.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 导出CSV",
                    data=csv,
                    file_name=f"缠论分析_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with export_cols[1]:
                # 生成并下载图片
                if st.button("📸 保存为图片", use_container_width=True):
                    with st.spinner("正在生成图片..."):
                        img_buf = generate_result_image(results)
                        if img_buf:
                            st.download_button(
                                label="⬇️ 下载图片",
                                data=img_buf,
                                file_name=f"缠论分析_{datetime.now().strftime('%Y%m%d_%H%M')}.png",
                                mime="image/png",
                                use_container_width=True
                            )
                        else:
                            st.error("生成图片失败")
            
            # 直接显示图片预览
            if buy3 or buy1:
                with st.expander("👀 图片预览（长按保存）", expanded=False):
                    img_buf = generate_result_image(results)
                    if img_buf:
                        st.image(img_buf, use_column_width=True)
        except Exception as e:
            st.error(f"表格生成出错: {str(e)}")
            # 显示原始数据作为备选
            st.write("原始数据:", results)
    else:
        # 欢迎页面
        st.info("👈 请在左侧配置股票池，然后点击「开始分析」")
        
        st.markdown("""
        ### 🎯 使用指南
        
        **1. 自定义股票池**
        - 选择预设模板（光模块、白酒、新能源等）
        - 或手动输入股票代码，格式：`000001,000002,600519`
        - 也可带名称：`000001平安银行,000002万科A`
        
        **2. 板块自动扫描**
        - 选择概念板块（如"光纤"、"芯片"）
        - 自动获取该板块所有成分股
        - 一键分析整个板块
        
        **3. 分析结果**
        - 🚀 三买：强势突破，关注买入机会
        - 📉 一买：底部反转，可能止跌反弹
        - 支持导出CSV数据
        
        ### ⚠️ 风险提示
        本工具仅供学习研究使用，不构成投资建议。股市有风险，投资需谨慎。
        """)

if __name__ == "__main__":
    main()
