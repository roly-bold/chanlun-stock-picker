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
import urllib.request
from datetime import datetime, timedelta
import tushare as ts
from pypinyin import lazy_pinyin, Style
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

def get_chinese_font():
    """获取中文字体路径 - 尝试多种方式，必要时下载"""
    import platform
    
    # 首先检查本地缓存字体
    data_dir = os.path.join(os.path.dirname(__file__), DATA_DIR)
    os.makedirs(data_dir, exist_ok=True)
    cached_font = os.path.join(data_dir, 'NotoSansCJK-Regular.otf')
    
    if os.path.exists(cached_font):
        return cached_font
    
    # 尝试系统字体
    font_paths = []
    
    if platform.system() == 'Windows':
        font_paths = [
            'C:/Windows/Fonts/simhei.ttf',
            'C:/Windows/Fonts/simsun.ttc',
            'C:/Windows/Fonts/msyh.ttc',
            'C:/Windows/Fonts/simkai.ttf',
            'C:/Windows/Fonts/deng.ttf',
        ]
    else:
        font_paths = [
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/System/Library/Fonts/PingFang.ttc',
            '/System/Library/Fonts/STHeiti Light.ttc',
            '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        ]
    
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    # 尝试下载 Google Noto Sans CJK 字体
    try:
        import urllib.request
        font_url = 'https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf'
        
        # 使用GitHub镜像加速
        mirror_urls = [
            'https://ghproxy.com/https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf',
            'https://mirror.ghproxy.com/https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf',
            font_url,
        ]
        
        for url in mirror_urls:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    with open(cached_font, 'wb') as f:
                        f.write(response.read())
                if os.path.exists(cached_font) and os.path.getsize(cached_font) > 1000000:  # 确保文件大于1MB
                    return cached_font
            except:
                continue
                
    except Exception:
        pass
    
    return None

def generate_result_image(results):
    """生成分析结果图片 - 使用PIL确保中文正常显示"""
    if not results:
        return None
    
    # 筛选有信号的股票
    buy3 = [r for r in results if r['signal'] == '三买']
    buy1 = [r for r in results if r['signal'] == '一买']
    
    # 如果没有信号股票，不生成图片
    if not buy3 and not buy1:
        return None
    
    # 获取字体
    font_path = get_chinese_font()
    
    # 图片尺寸
    width = 800
    signal_count = len(buy3) + len(buy1)
    height = 200 + signal_count * 120  # 每个信号卡片约120像素
    
    # 创建白色背景图片
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    
    # 尝试加载字体
    try:
        if font_path:
            font_title = ImageFont.truetype(font_path, 28)
            font_subtitle = ImageFont.truetype(font_path, 18)
            font_stock = ImageFont.truetype(font_path, 20)
            font_info = ImageFont.truetype(font_path, 16)
            font_small = ImageFont.truetype(font_path, 12)
        else:
            raise IOError("No Chinese font found")
    except:
        # 使用默认字体（可能不支持中文）
        font_title = ImageFont.load_default()
        font_subtitle = font_title
        font_stock = font_title
        font_info = font_title
        font_small = font_title
    
    # 颜色定义
    color_title = '#2c3e50'
    color_green = '#27ae60'
    color_orange = '#e67e22'
    color_gray = '#7f8c8d'
    color_dark = '#2c3e50'
    color_red = '#e74c3c'
    color_bg_green = '#e8f5e9'
    color_bg_orange = '#fff3e0'
    
    y_pos = 20
    
    # 标题
    draw.text((width//2, y_pos), '缠论选股分析结果', fill=color_title, font=font_title, anchor='mm')
    y_pos += 40
    
    # 时间
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    draw.text((width//2, y_pos), time_str, fill=color_gray, font=font_small, anchor='mm')
    y_pos += 30
    
    # 统计信息
    stats_text = f'分析:{len(results)}只 | 三买:{len(buy3)}只 | 一买:{len(buy1)}只'
    draw.text((width//2, y_pos), stats_text, fill=color_dark, font=font_subtitle, anchor='mm')
    y_pos += 40
    
    def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
        """绘制圆角矩形"""
        x1, y1, x2, y2 = xy
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    
    # 三买股票
    if buy3:
        draw.text((40, y_pos), '【三买信号-强势突破】', fill=color_green, font=font_stock)
        y_pos += 35
        
        for r in buy3:
            # 绘制卡片背景
            card_margin = 30
            card_height = 90
            draw.rounded_rectangle(
                [card_margin, y_pos, width - card_margin, y_pos + card_height],
                radius=10, fill=color_bg_green, outline='#c8e6c9', width=2
            )
            
            # 股票信息
            price_color = color_red if r['change'] > 0 else color_green
            line1 = f"{r['code']} {r['name']}   ¥{r['price']:.2f} ({r['change']:+.1f}%)"
            draw.text((card_margin + 15, y_pos + 10), line1, fill=color_dark, font=font_stock)
            
            # 买卖点信息 - 三列布局
            info_y = y_pos + 45
            col_width = (width - 2 * card_margin - 30) // 3
            
            # 买入
            buy_text = f"买入: ¥{r['price']:.1f}"
            draw.text((card_margin + 15, info_y), buy_text, fill=color_green, font=font_info)
            
            # 止损
            if r.get('stop_loss'):
                stop_text = f"止损: ¥{r.get('stop_loss', 0):.1f} ({r.get('stop_loss_pct', 0):+.0f}%)"
                draw.text((card_margin + 15 + col_width, info_y), stop_text, fill=color_red, font=font_info)
            
            # 目标
            if r.get('target_price'):
                target_text = f"目标: ¥{r.get('target_price', 0):.1f} (+{r.get('target_pct', 0):.0f}%)"
                draw.text((card_margin + 15 + col_width * 2, info_y), target_text, fill='#1976d2', font=font_info)
            
            y_pos += card_height + 15
    
    # 一买股票
    if buy1:
        y_pos += 10
        draw.text((40, y_pos), '【一买信号-底部反转】', fill=color_orange, font=font_stock)
        y_pos += 35
        
        for r in buy1:
            # 绘制卡片背景
            card_margin = 30
            card_height = 90
            draw.rounded_rectangle(
                [card_margin, y_pos, width - card_margin, y_pos + card_height],
                radius=10, fill=color_bg_orange, outline='#ffe0b2', width=2
            )
            
            # 股票信息
            price_color = color_red if r['change'] > 0 else color_green
            line1 = f"{r['code']} {r['name']}   ¥{r['price']:.2f} ({r['change']:+.1f}%)"
            draw.text((card_margin + 15, y_pos + 10), line1, fill=color_dark, font=font_stock)
            
            # 买卖点信息
            info_y = y_pos + 45
            col_width = (width - 2 * card_margin - 30) // 3
            
            # 买入
            buy_text = f"买入: ¥{r['price']:.1f}"
            draw.text((card_margin + 15, info_y), buy_text, fill=color_green, font=font_info)
            
            # 止损
            if r.get('stop_loss'):
                stop_text = f"止损: ¥{r.get('stop_loss', 0):.1f} ({r.get('stop_loss_pct', 0):+.0f}%)"
                draw.text((card_margin + 15 + col_width, info_y), stop_text, fill=color_red, font=font_info)
            
            # 目标
            if r.get('target_price'):
                target_text = f"目标: ¥{r.get('target_price', 0):.1f} (+{r.get('target_pct', 0):.0f}%)"
                draw.text((card_margin + 15 + col_width * 2, info_y), target_text, fill='#1976d2', font=font_info)
            
            y_pos += card_height + 15
    
    # 风险提示
    y_pos += 20
    warning = '风险提示：以上分析仅供参考，不构成投资建议。'
    draw.text((width//2, y_pos), warning, fill='#e74c3c', font=font_small, anchor='mm')
    
    # 保存为图片
    buf = io.BytesIO()
    img.save(buf, format='PNG', quality=95)
    buf.seek(0)
    
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
    """获取板块成分股 - 支持申万行业和概念板块"""
    try:
        # 跳过分隔符选项
        if concept_name.startswith("==="):
            return None
            
        # 1. 先尝试概念板块（同花顺/东方财富概念）
        try:
            concepts = pro.concept()
            matched = concepts[concepts['name'].str.contains(concept_name, na=False, case=False)]
            
            if not matched.empty:
                concept_code = matched.iloc[0]['code']
                detail = pro.concept_detail(id=concept_code, fields='ts_code,name')
                
                if detail is not None and not detail.empty:
                    stock_list = []
                    for _, row in detail.iterrows():
                        symbol = row['ts_code'].split('.')[0]
                        stock_list.append((symbol, row['name']))
                    return stock_list
        except:
            pass
        
        # 2. 尝试申万行业分类
        try:
            # 获取申万一级行业列表
            sw_index = pro.index_classify(level='L1', src='SW2021')
            if sw_index is not None and not sw_index.empty:
                # 模糊匹配行业名称
                matched = sw_index[sw_index['industry_name'].str.contains(concept_name, na=False, case=False)]
                if matched.empty:
                    # 尝试精确匹配
                    matched = sw_index[sw_index['industry_name'] == concept_name]
                
                if not matched.empty:
                    industry_code = matched.iloc[0]['index_code']
                    # 获取行业成分股
                    members = pro.index_member(index_code=industry_code, fields='con_code,con_name')
                    if members is not None and not members.empty:
                        stock_list = []
                        for _, row in members.iterrows():
                            symbol = row['con_code'].split('.')[0]
                            stock_list.append((symbol, row['con_name']))
                        return stock_list
        except:
            pass
        
        # 3. 尝试申万二级行业（如果一级没找到）
        try:
            sw_index2 = pro.index_classify(level='L2', src='SW2021')
            if sw_index2 is not None and not sw_index2.empty:
                matched = sw_index2[sw_index2['industry_name'].str.contains(concept_name, na=False, case=False)]
                if not matched.empty:
                    industry_code = matched.iloc[0]['index_code']
                    members = pro.index_member(index_code=industry_code, fields='con_code,con_name')
                    if members is not None and not members.empty:
                        stock_list = []
                        for _, row in members.iterrows():
                            symbol = row['con_code'].split('.')[0]
                            stock_list.append((symbol, row['con_name']))
                        return stock_list
        except:
            pass
            
        # 4. 尝试标准行业分类（证监会行业）
        try:
            stock_list_data = pro.stock_company(fields='ts_code,chairman,manager,secretary,reg_capital,setup_date,province,city,website,email,office,employees,main_business,business_scope')
            if stock_list_data is not None and not stock_list_data.empty:
                # 这里可以根据业务范围筛选，但比较复杂，暂时跳过
                pass
        except:
            pass
        
        return None
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
        
        # 常用概念列表 - 申万行业分类 + 热门概念
        # 申万一级行业（2021版）31个行业分类
        sw_industries = [
            # 上游资源
            "煤炭", "石油石化", "有色金属", "钢铁",
            # 中游制造  
            "基础化工", "建筑材料", "建筑装饰", "电力设备", "机械设备", "国防军工",
            # 下游消费
            "汽车", "家用电器", "纺织服饰", "轻工制造", "医药生物", "食品饮料", 
            "农林牧渔", "商贸零售", "社会服务",
            # 大金融
            "银行", "非银金融", "房地产",
            # TMT
            "电子", "计算机", "通信", "传媒",
            # 公用事业 & 环保
            "公用事业", "交通运输", "环保",
            # 其他
            "综合"
        ]
        
        # 热门概念板块（市场热点）
        hot_concepts = [
            "芯片", "半导体", "人工智能", "新能源", "光伏", "储能",
            "5G", "云计算", "大数据", "区块链", "元宇宙",
            "新能源汽车", "锂电池", "特斯拉", "比亚迪",
            "军工", "航天", "航母",
            "医药", "创新药", "医疗器械", "CRO",
            "白酒", "食品", "预制菜",
            "银行", "证券", "保险", "金融科技",
            "稀土", "石墨烯", "碳纤维",
            "数字货币", "国产软件", "网络安全",
            "工业互联网", "智能制造", "机器人",
            "充电桩", "氢能源", "燃料电池",
            "医美", "化妆品", "宠物经济",
            "养老", "三胎", "教育",
            "碳中和", "垃圾分类", "污水处理",
            "一带一路", "京津冀", "长三角", "粤港澳大湾区",
            "新材料", "3D打印", "纳米技术",
            "量子计算", "边缘计算", "算力",
            "卫星导航", "北斗", "通信设备",
            "游戏", "影视", "动漫", "短视频",
            "电子商务", "直播带货", "社区团购",
            "快递", "物流", "冷链",
            "有色·铜", "有色·铝", "黄金", "白银",
            "农业", "养殖", "种植", "化肥",
            "电力", "风电", "水电", "核电", "火电",
            "玻璃", "水泥", "钢铁", "煤炭",
            "纺织", "服装", "家纺", "鞋帽",
            "家具", "造纸", "包装", "印刷",
            "工程机械", "重型机械", "专用设备",
            "航空", "船舶", "轨道交通",
            "石油", "天然气", "页岩气",
            "化工", "塑料", "橡胶", "化纤",
            "建材", "装修", "装配式建筑"
        ]
        
        # 合并所有选项，按类别分组
        concept_options = ["=== 申万一级行业 ==="] + sw_industries + ["=== 热门概念 ==="] + hot_concepts
        
        concept_name = st.sidebar.selectbox("选择概念板块", concept_options)
        
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
                    
                    # 第二行：买卖点 - 醒目样式
                    st.markdown("""
                        <style>
                        .trade-info-row { display: flex; gap: 8px; margin: 8px 0; }
                        .trade-box {
                            flex: 1;
                            padding: 10px 12px;
                            border-radius: 8px;
                            font-size: 15px;
                            font-weight: 600;
                        }
                        .buy-box { background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); color: #2e7d32; border-left: 4px solid #4caf50; }
                        .stop-box { background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); color: #c62828; border-left: 4px solid #ef5350; }
                        .target-box { background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); color: #1565c0; border-left: 4px solid #42a5f5; }
                        .trade-label { font-size: 12px; opacity: 0.8; margin-bottom: 2px; }
                        .trade-value { font-size: 16px; font-weight: 700; }
                        </style>
                        <div class="trade-info-row">
                            <div class="trade-box buy-box">
                                <div class="trade-label">💰 买入</div>
                                <div class="trade-value">¥{:.2f}</div>
                            </div>
                            <div class="trade-box stop-box">
                                <div class="trade-label">🛑 止损</div>
                                <div class="trade-value">¥{:.1f} ({:+.0f}%)</div>
                            </div>
                            <div class="trade-box target-box">
                                <div class="trade-label">🎯 目标</div>
                                <div class="trade-value">¥{:.1f} (+{:.0f}%)</div>
                            </div>
                        </div>
                    """.format(
                        r['price'],
                        r.get('stop_loss', 0), r.get('stop_loss_pct', 0),
                        r.get('target_price', 0), r.get('target_pct', 0)
                    ), unsafe_allow_html=True)
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
                    
                    # 第二行：买卖点 - 醒目样式
                    st.markdown("""
                        <style>
                        .trade-info-row { display: flex; gap: 8px; margin: 8px 0; }
                        .trade-box {
                            flex: 1;
                            padding: 10px 12px;
                            border-radius: 8px;
                            font-size: 15px;
                            font-weight: 600;
                        }
                        .buy-box { background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); color: #2e7d32; border-left: 4px solid #4caf50; }
                        .stop-box { background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); color: #c62828; border-left: 4px solid #ef5350; }
                        .target-box { background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); color: #1565c0; border-left: 4px solid #42a5f5; }
                        .trade-label { font-size: 12px; opacity: 0.8; margin-bottom: 2px; }
                        .trade-value { font-size: 16px; font-weight: 700; }
                        </style>
                        <div class="trade-info-row">
                            <div class="trade-box buy-box">
                                <div class="trade-label">💰 买入</div>
                                <div class="trade-value">¥{:.2f}</div>
                            </div>
                            <div class="trade-box stop-box">
                                <div class="trade-label">🛑 止损</div>
                                <div class="trade-value">¥{:.1f} ({:+.0f}%)</div>
                            </div>
                            <div class="trade-box target-box">
                                <div class="trade-label">🎯 目标</div>
                                <div class="trade-value">¥{:.1f} (+{:.0f}%)</div>
                            </div>
                        </div>
                    """.format(
                        r['price'],
                        r.get('stop_loss', 0), r.get('stop_loss_pct', 0),
                        r.get('target_price', 0), r.get('target_pct', 0)
                    ), unsafe_allow_html=True)
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
