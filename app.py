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

# ========== 导入缠论算法优化器 ==========
from chanlun_optimizer import ChanLunOptimizer, SignalScore

# 尝试导入efinance或akshare获取实时数据
try:
    import efinance as ef
    REALTIME_DATA_SOURCE = "efinance"
except ImportError:
    try:
        import akshare as ak
        REALTIME_DATA_SOURCE = "akshare"
    except ImportError:
        REALTIME_DATA_SOURCE = None

# ========== 2026年热点主线板块配置 ==========
SECTOR_GROUPS = {
    "科技成长": {
        "sectors": ["半导体", "计算机应用", "国防军工", "通信设备", "电子", "计算机", "传媒"],
        "weight": 1.2,  # 评分加权
        "description": "AI应用、国产替代、科技自主"
    },
    "周期复苏": {
        "sectors": ["有色金属", "基础化工", "石油石化", "钢铁", "煤炭", "建筑材料"],
        "weight": 1.0,
        "description": "大宗商品、基建复苏、产能出清"
    },
    "核心资产": {
        "sectors": ["食品饮料", "非银金融", "生物医药", "家用电器", "医药生物", "银行"],
        "weight": 1.1,
        "description": "消费复苏、高股息、防御配置"
    },
    "新质生产力": {
        "sectors": ["电力设备", "机械设备", "汽车零部件", "轻工制造", "汽车", "环保"],
        "weight": 1.15,
        "description": "新能源、智能制造、绿色转型"
    },
    "未来产业": {
        "sectors": ["商业航天", "低空经济", "人形机器人", "固态电池", "脑机接口", "量子通信", "可控核聚变"],
        "weight": 1.3,
        "description": "2026高增长赛道、主题投资"
    }
}

# ========== 2026核心赛道精选股票池 ==========
SELECTED_STOCKS = {
    "科技硬核": {
        "codes": ["603501", "688012", "300308", "300339", "603986"],
        "names": ["韦尔股份", "中微公司", "中际旭创", "润和软件", "兆易创新"],
        "description": "半导体龙头+AI算力+国产替代"
    },
    "新质生产力": {
        "codes": ["300750", "601012", "002466", "002812", "600438"],
        "names": ["宁德时代", "隆基绿能", "天齐锂业", "恩捷股份", "通威股份"],
        "description": "新能源+储能+锂电材料"
    },
    "自主可控/军工": {
        "codes": ["600893", "002179", "600760", "000063", "600150"],
        "names": ["航发动力", "中航光电", "中航沈飞", "中兴通讯", "中国船舶"],
        "description": "军工龙头+通信设备+高端装备"
    },
    "核心资产/消费": {
        "codes": ["600519", "000858", "600030", "601318", "600276"],
        "names": ["贵州茅台", "五粮液", "中信证券", "中国平安", "恒瑞医药"],
        "description": "白酒+券商+保险+医药龙头"
    },
    "周期反转/资源": {
        "codes": ["601899", "603993", "600547", "601600", "000426"],
        "names": ["紫金矿业", "洛阳钼业", "山东黄金", "中国铝业", "兴业银锡"],
        "description": "有色龙头+贵金属+战略资源"
    }
}

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
    
    # 筛选有信号的股票（兼容新的评分格式和二买）
    buy2_strong = [r for r in results if r['signal'] == '强力二买']
    buy2_standard = [r for r in results if r['signal'] == '标准二买']
    buy3 = [r for r in results if '三买' in r['signal'] and r.get('signal_grade') in ['A', 'B']]
    buy3_low = [r for r in results if '三买' in r['signal'] and r.get('signal_grade') in ['C', 'D']]
    buy1 = [r for r in results if r['signal'] == '一买']
    
    # 如果没有信号股票，不生成图片
    if not buy2_strong and not buy2_standard and not buy3 and not buy1 and not buy3_low:
        return None
    
    # 获取字体
    font_path = get_chinese_font()
    
    # 图片尺寸 - 增加二买信号的高度
    width = 800
    signal_count = len(buy2_strong) + len(buy2_standard) + len(buy3) + len(buy1)
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
    total_signals = len(buy2_strong) + len(buy2_standard) + len(buy3) + len(buy3_low) + len(buy1)
    stats_text = f'分析:{len(results)}只 | 强力二买:{len(buy2_strong)}只 | 标准二买:{len(buy2_standard)}只 | 三买:{len(buy3)+len(buy3_low)}只 | 一买:{len(buy1)}只'
    draw.text((width//2, y_pos), stats_text, fill=color_dark, font=font_subtitle, anchor='mm')
    y_pos += 40
    
    def draw_rounded_rect(draw, xy, radius, fill, outline=None, width=1):
        """绘制圆角矩形"""
        x1, y1, x2, y2 = xy
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    
    # 强力二买股票（核心买点）
    if buy2_strong:
        draw.text((40, y_pos), '【强力二买-核心买点】', fill=color_green, font=font_stock)
        y_pos += 35
        
        for r in buy2_strong:
            card_margin = 30
            card_height = 90
            draw.rounded_rectangle(
                [card_margin, y_pos, width - card_margin, y_pos + card_height],
                radius=10, fill=color_bg_green, outline='#c8e6c9', width=2
            )
            
            price_color = color_red if r['change'] > 0 else color_green
            line1 = f"{r['code']} {r['name']}   ¥{r['price']:.2f} ({r['change']:+.1f}%)"
            draw.text((card_margin + 15, y_pos + 10), line1, fill=color_dark, font=font_stock)
            
            info_y = y_pos + 45
            col_width = (width - 2 * card_margin - 30) // 3
            
            buy_text = f"买入: ¥{r['price']:.1f}"
            draw.text((card_margin + 15, info_y), buy_text, fill=color_green, font=font_info)
            
            if r.get('stop_loss'):
                stop_text = f"止损: ¥{r.get('stop_loss', 0):.1f}"
                draw.text((card_margin + 15 + col_width, info_y), stop_text, fill=color_red, font=font_info)
            
            if r.get('target_price'):
                target_text = f"目标: ¥{r.get('target_price', 0):.1f}"
                draw.text((card_margin + 15 + col_width * 2, info_y), target_text, fill='#1976d2', font=font_info)
            
            y_pos += card_height + 15
    
    # 标准二买股票
    if buy2_standard:
        y_pos += 10
        draw.text((40, y_pos), '【标准二买-有效买点】', fill=color_orange, font=font_stock)
        y_pos += 35
        
        for r in buy2_standard:
            card_margin = 30
            card_height = 90
            draw.rounded_rectangle(
                [card_margin, y_pos, width - card_margin, y_pos + card_height],
                radius=10, fill=color_bg_orange, outline='#ffcc80', width=2
            )
            
            price_color = color_red if r['change'] > 0 else color_green
            line1 = f"{r['code']} {r['name']}   ¥{r['price']:.2f} ({r['change']:+.1f}%)"
            draw.text((card_margin + 15, y_pos + 10), line1, fill=color_dark, font=font_stock)
            
            info_y = y_pos + 45
            col_width = (width - 2 * card_margin - 30) // 3
            
            buy_text = f"买入: ¥{r['price']:.1f}"
            draw.text((card_margin + 15, info_y), buy_text, fill=color_green, font=font_info)
            
            if r.get('stop_loss'):
                stop_text = f"止损: ¥{r.get('stop_loss', 0):.1f}"
                draw.text((card_margin + 15 + col_width, info_y), stop_text, fill=color_red, font=font_info)
            
            if r.get('target_price'):
                target_text = f"目标: ¥{r.get('target_price', 0):.1f}"
                draw.text((card_margin + 15 + col_width * 2, info_y), target_text, fill='#1976d2', font=font_info)
            
            y_pos += card_height + 15
    
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
    
    # 三买低评分股票（谨慎）
    if buy3_low:
        y_pos += 10
        draw.text((40, y_pos), '【三买信号-谨慎参与(C/D级)】', fill=color_orange, font=font_stock)
        y_pos += 35
        
        for r in buy3_low:
            # 绘制卡片背景
            card_margin = 30
            card_height = 90
            draw.rounded_rectangle(
                [card_margin, y_pos, width - card_margin, y_pos + card_height],
                radius=10, fill=color_bg_orange, outline='#ffcc80', width=2
            )
            
            # 股票信息
            price_color = color_red if r['change'] > 0 else color_green
            grade = r.get('signal_grade', '?')
            line1 = f"{r['code']} {r['name']}   ¥{r['price']:.2f} ({r['change']:+.1f}%) [评分:{grade}]"
            draw.text((card_margin + 15, y_pos + 10), line1, fill=color_dark, font=font_stock)
            
            # 买卖点信息
            info_y = y_pos + 45
            col_width = (width - 2 * card_margin - 30) // 3
            
            if r.get('stop_loss'):
                stop_text = f"止损: ¥{r.get('stop_loss', 0):.1f}"
                draw.text((card_margin + 15, info_y), stop_text, fill=color_red, font=font_info)
            
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

def calculate_macd(df, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    df = df.copy()
    df['ema_fast'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    return df

def calculate_stroke_macd_area(df, stroke_start_idx, stroke_end_idx):
    """计算笔对应的MACD面积（用于背驰判断）"""
    if stroke_start_idx < 0 or stroke_end_idx >= len(df) or stroke_start_idx >= stroke_end_idx:
        return 0, 0
    
    macd_data = df.iloc[stroke_start_idx:stroke_end_idx+1]['macd_hist']
    
    # 计算红绿柱面积（绝对值之和）
    positive_area = macd_data[macd_data > 0].sum()  # 红柱面积
    negative_area = abs(macd_data[macd_data < 0].sum())  # 绿柱面积
    
    return positive_area, negative_area

def check_divergence(df, strokes, zhongshu):
    """
    检查背驰信号
    返回: {
        'has_divergence': bool,
        'divergence_type': str,  # '底背驰' 或 '顶背驰'
        'divergence_strength': str,  # '强' 或 '弱'
        'explanation': str
    }
    """
    if len(strokes) < 2:
        return {'has_divergence': False, 'divergence_type': None, 'divergence_strength': None, 'explanation': ''}
    
    result = {'has_divergence': False, 'divergence_type': None, 'divergence_strength': None, 'explanation': ''}
    
    # 获取最近的两笔下跌（用于底背驰判断）
    down_strokes = [s for s in strokes if s['type'] == 'down']
    
    if len(down_strokes) >= 2:
        # 取最近两笔下跌
        last_down = down_strokes[-1]
        prev_down = down_strokes[-2]
        
        # 价格创新低判断
        price_new_low = last_down['end'] < prev_down['end']
        
        # 获取对应的MACD数据（简化处理，用笔的终点附近数据）
        # 实际应该用分型对应的具体K线位置
        current_price_drop = abs(last_down['end'] - last_down['start'])
        prev_price_drop = abs(prev_down['end'] - prev_down['start'])
        
        # 简化背驰判断：后一笔价格跌幅更大，但MACD面积更小
        # 这里用价格跌幅和MACD柱状体高度来近似
        if price_new_low and current_price_drop > prev_price_drop * 0.8:
            # 检查是否在中枢下方（一买区域）
            current_price = df.iloc[-1]['close']
            if current_price < zhongshu['low']:
                result['has_divergence'] = True
                result['divergence_type'] = '底背驰'
                result['divergence_strength'] = '中'
                result['explanation'] = f'价格创新低但力度减弱，可能形成一买背驰'
    
    # 获取最近的两笔上涨（用于顶背驰判断）
    up_strokes = [s for s in strokes if s['type'] == 'up']
    
    if len(up_strokes) >= 2:
        last_up = up_strokes[-1]
        prev_up = up_strokes[-2]
        
        # 价格创新高判断
        price_new_high = last_up['end'] > prev_up['end']
        
        current_price_rise = last_up['end'] - last_up['start']
        prev_price_rise = prev_up['end'] - prev_up['start']
        
        if price_new_high and current_price_rise < prev_price_rise * 1.2:
            current_price = df.iloc[-1]['close']
            if current_price > zhongshu['high']:
                result['has_divergence'] = True
                result['divergence_type'] = '顶背驰'
                result['divergence_strength'] = '中'
                result['explanation'] = f'价格创新高但力度减弱，可能形成背驰卖点'
    
    return result

def check_sell_signals(df, strokes, zhongshu):
    """
    检查卖出信号（三卖）
    三卖定义：向下离开中枢后，反弹（向上笔）不回到中枢内
    """
    if len(strokes) < 3:
        return {'has_sell_signal': False, 'sell_type': None, 'explanation': ''}
    
    result = {'has_sell_signal': False, 'sell_type': None, 'explanation': ''}
    
    current_price = df.iloc[-1]['close']
    
    # 获取最近三笔
    recent_strokes = strokes[-3:]
    
    # 三卖判断：向下离开中枢 + 反弹不回中枢
    # 模式：down -> up -> down (当前在最后一笔下跌中)
    if (recent_strokes[0]['type'] == 'down' and 
        recent_strokes[1]['type'] == 'up' and 
        recent_strokes[2]['type'] == 'down'):
        
        # 第一笔向下离开中枢
        first_down_low = recent_strokes[0]['end']
        # 第二笔反弹高点
        rebound_high = recent_strokes[1]['end']
        
        # 判断：反弹高点低于中枢下沿（不回中枢）
        if rebound_high < zhongshu['low'] and current_price < rebound_high:
            result['has_sell_signal'] = True
            result['sell_type'] = '三卖'
            result['explanation'] = '向下离开中枢后反弹未回中枢，三卖信号'
    
    # 二卖判断（简化）：向上突破中枢后，回抽跌破中枢上沿
    if (recent_strokes[0]['type'] == 'up' and 
        recent_strokes[1]['type'] == 'down'):
        
        up_high = recent_strokes[0]['end']
        down_low = recent_strokes[1]['end']
        
        # 向上突破后回抽到中枢内
        if up_high > zhongshu['high'] and down_low < zhongshu['high'] and down_low > zhongshu['low']:
            if current_price < zhongshu['high']:
                result['has_sell_signal'] = True
                result['sell_type'] = '二卖'
                result['explanation'] = '突破后回抽至中枢内，二卖信号'
    
    return result

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
        
        # 计算MACD
        df = calculate_macd(df)
        
        # 检查背驰信号
        divergence = check_divergence(df, strokes, zhongshu)
        
        # 检查卖出信号（三卖、二卖）
        sell_signal = check_sell_signals(df, strokes, zhongshu)
        
        # ========== 初始化缠论优化器 ==========
        optimizer = ChanLunOptimizer()
        
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
        divergence_info = ""
        sell_signal_info = ""
        signal_score = None  # 新增：信号评分
        
        # 优先级：卖出信号 > 三买 > 一买（带背驰）
        
        # 1. 先检查卖出信号（三卖、二卖）- 优化版：评分系统
        if sell_signal['has_sell_signal']:
            signal_type = sell_signal['sell_type']  # "三卖" 或 "二卖"
            
            # 卖出信号评分（简化版，主要依据跌破幅度和回抽情况）
            breakout_pct = abs((current_price - zhongshu['low']) / zhongshu['low'] * 100) if current_price < zhongshu['low'] else 0
            
            context = {
                'breakout_pct': breakout_pct,
                'current_vol': df.iloc[-1]['volume'] if 'volume' in df.columns else 0,
                'ma20_vol': df.iloc[-1]['volume'] if 'volume' in df.columns else 1,
                'rebound_pct': 0,  # 需要计算回抽幅度
                'market_trend': 'neutral'
            }
            
            if context['ma20_vol'] == 0 or pd.isna(context['ma20_vol']):
                context['ma20_vol'] = 1
            
            signal_score = optimizer.score_sell_signal(context)
            
            # 根据评分调整信号
            if signal_type == '三卖':
                if signal_score.grade in ['A', 'B']:
                    signal = f"三卖(评分:{signal_score.grade})"
                    action = "卖出"
                    risk_level = "高"
                else:
                    signal = f"三卖(评分:{signal_score.grade})"
                    action = "减仓"
                    risk_level = "中"
            else:
                signal = signal_type  # 保持原有二卖标记
                action = "减仓"
                risk_level = "中"
            
            sell_signal_info = sell_signal['explanation']
            suggestion = f"{signal_score.action} | 预估成功率{signal_score.probability*100:.0f}% | {sell_signal['explanation']}"
            
            # 卖出建议
            entry_price = current_price
            # 止损设在近期反弹高点
            recent_up = [s for s in strokes if s['type'] == 'up']
            if recent_up:
                stop_loss = recent_up[-1]['end'] * 1.02  # 反弹高点上方2%
            else:
                stop_loss = current_price * 1.05
            stop_loss_pct = (stop_loss - current_price) / current_price * 100
            
            # 目标：向下空间较大
            target_price = min_price * 0.95
            target_pct = (target_price - current_price) / current_price * 100
        
        # 2. 三买信号（向上离开中枢）- 优化版：动态阈值+评分系统
        elif current_price > zhongshu['high'] and strokes:
            recent_up = [s for s in strokes if s['type'] == 'up']
            if recent_up and recent_up[-1]['end'] > zhongshu['high']:
                # 计算突破幅度（相对于中枢上沿）
                breakout_pct = (current_price - zhongshu['high']) / zhongshu['high'] * 100
                
                # 计算距离历史高点的距离
                distance_to_max = (max_price - current_price) / max_price * 100 if max_price > 0 else 0
                
                # 获取动态阈值
                threshold = optimizer.get_dynamic_threshold(df, symbol)
                
                # 检查突破是否有效（基于动态阈值）
                is_valid, reason = optimizer.is_valid_breakout(breakout_pct, threshold, '三买')
                
                if not is_valid:
                    # 突破幅度不合适，降级为观察
                    if breakout_pct >= threshold['三买_max']:
                        signal = "突破后观察"
                        action = "观望"
                        suggestion = f"已突破{breakout_pct:.1f}%（超过{threshold['description']}阈值{threshold['三买_max']}%），追高风险"
                        risk_level = "高"
                    else:
                        signal = "突破不足"
                        action = "观望"
                        suggestion = reason
                        risk_level = "中"
                else:
                    # 突破有效，进行信号评分
                    context = {
                        'breakout_pct': breakout_pct,
                        'current_vol': df.iloc[-1]['volume'] if 'volume' in df.columns else 0,
                        'ma20_vol': df['volume'].rolling(20).mean().iloc[-1] if 'volume' in df.columns else 1,
                        'sublevel_confirm': False,  # 暂不支持，后续可接入
                        'market_trend': 'neutral',  # 可接入大盘数据
                        'distance_to_max': distance_to_max
                    }
                    
                    # 处理成交量数据可能为0的情况
                    if context['ma20_vol'] == 0 or pd.isna(context['ma20_vol']):
                        context['ma20_vol'] = 1
                    
                    signal_score = optimizer.score_buy_signal(context)
                    
                    # 检查是否背驰
                    if divergence['has_divergence'] and divergence['divergence_type'] == '顶背驰':
                        signal = f"三买+背驰(评分:{signal_score.grade})"
                        action = "减仓"
                        divergence_info = divergence['explanation']
                        suggestion = f"三买但出现顶背驰，建议减仓而非加仓 | {signal_score.action}"
                        risk_level = "高"
                    else:
                        # 根据评分确定信号强度
                        if signal_score.grade in ['A', 'B']:
                            signal = f"三买(评分:{signal_score.grade})"
                            action = "买入"
                            risk_level = "低" if signal_score.grade == 'A' else "中"
                        else:
                            signal = f"三买(评分:{signal_score.grade})"
                            action = "观望" if signal_score.grade == 'D' else "关注"
                            risk_level = "高"
                        
                        suggestion = f"{signal_score.action} | 预估成功率{signal_score.probability*100:.0f}% | 突破{breakout_pct:.1f}%"
                    
                    # 买入建议
                    entry_price = current_price
                    # 止损：中枢上沿下方2%或-5%取较大值
                    stop_loss = max(zhongshu['high'] * 0.98, current_price * 0.95)
                    stop_loss_pct = (stop_loss - current_price) / current_price * 100
                    
                    # 目标：前期高点
                    target_price = max_price
                    target_pct = (target_price - current_price) / current_price * 100
                    
                    # 记录评分详情（用于显示）
                    score_details = " | ".join(signal_score.details[:3]) if signal_score else ""
                    if score_details:
                        suggestion += f"\n💡 {score_details}"
        
        # 3. 二买信号（核心信号）- 架构师优化版
        # 基于动态分型 + 力度衰竭的精确判断
        elif strokes and len(strokes) >= 3 and len(df) >= 5:
            # 获取最近三笔：down(一买) -> up(反弹) -> down(回抽)
            recent_strokes = strokes[-3:]
            
            if (recent_strokes[0]['type'] == 'down' and 
                recent_strokes[1]['type'] == 'up' and 
                recent_strokes[2]['type'] == 'down'):
                
                # 一买位置索引和低点
                first_buy_idx = recent_strokes[0]['end_idx']
                first_buy_low = recent_strokes[0]['end']
                # 当前检查位置（最新数据）
                i = len(df) - 1
                current_low = df['low'].iloc[i]
                
                # 修正后的二买逻辑：动态分型 + 力度衰竭
                # 1. 核心条件：不破一买最低点
                if current_low > first_buy_low and i >= 2 and first_buy_idx >= 2:
                    # 2. 确认底分型 (K线三笔重叠判断)
                    is_bottom_fractal = (df['low'].iloc[i-1] < df['low'].iloc[i-2] and 
                                         df['low'].iloc[i-1] < df['low'].iloc[i])
                    
                    # 3. 力度衰竭：当前回踩的MACD绿柱面积明显小于一买时期
                    is_fading = False
                    if 'macd_hist' in df.columns:
                        curr_macd_hist = abs(df['macd_hist'].iloc[i-2:i+1].sum())
                        prev_macd_hist = abs(df['macd_hist'].iloc[first_buy_idx-2:first_buy_idx+1].sum())
                        is_fading = curr_macd_hist < prev_macd_hist
                    
                    if is_bottom_fractal and is_fading:
                        # 4. 强弱分类
                        center_high = zhongshu['high']
                        
                        if current_low > center_high:
                            # 强力二买：不进中枢
                            signal = "强力二买"
                            action = "买入"
                            risk_level = "低"
                            suggestion = f"强力二买确认！回抽不破中枢上沿(¥{center_high:.2f})，底分型+MACD衰竭，高确定性买点"
                        else:
                            # 标准二买：回踩中枢不破底
                            signal = "标准二买"
                            action = "买入"
                            risk_level = "中"
                            distance_to_zhongshu = (center_high - current_low) / (center_high - zhongshu['low']) * 100 if center_high > zhongshu['low'] else 0
                            suggestion = f"标准二买确认！回抽进入中枢({distance_to_zhongshu:.1f}%)，底分型+MACD衰竭，有效买点"
                        
                        # 买入建议
                        entry_price = current_price
                        stop_loss = first_buy_low * 0.98
                        stop_loss_pct = (stop_loss - current_price) / current_price * 100
                        
                        # 目标位设置
                        if current_low > center_high:
                            target_price = max_price
                        else:
                            target_price = center_high
                        target_pct = (target_price - current_price) / current_price * 100
        
        # 4. 一买信号（向下离开中枢，带背驰更好）
        elif current_price < zhongshu['low'] and strokes:
            recent_down = [s for s in strokes if s['type'] == 'down']
            if recent_down:
                recent_low = recent_down[-1]['end']
                rebound_pct = (current_price - recent_low) / recent_low * 100
                
                # 检查是否背驰（底背驰）
                has_divergence = divergence['has_divergence'] and divergence['divergence_type'] == '底背驰'
                
                if rebound_pct > 1 or has_divergence:
                    if has_divergence:
                        signal = "一买+背驰"
                        action = "买入"  # 背驰加强信号
                        divergence_info = divergence['explanation']
                        risk_level = "中"
                        suggestion = "底背驰确认，反弹概率高"
                    else:
                        signal = "一买"
                        action = "关注"
                        risk_level = "高"
                        suggestion = "超跌反弹，小仓位试水"
                    
                    # 买入建议
                    entry_price = current_price
                    # 止损：前低下方3%
                    stop_loss = recent_low * 0.97
                    stop_loss_pct = (stop_loss - current_price) / current_price * 100
                    
                    # 目标：中枢下沿
                    target_price = zhongshu['low']
                    target_pct = (target_price - current_price) / current_price * 100
                    
                    if target_pct < 3 and not has_divergence:
                        suggestion = "反弹空间有限，建议观望"
        
        # 获取股票板块信息（用于后续筛选）
        sector_info = get_stock_sector_info(symbol)
        
        return {
            'code': symbol, 'name': name, 'price': current_price, 'change': current_chg,
            'max_price': max_price, 'min_price': min_price,
            'ding_count': ding_count, 'di_count': di_count, 'stroke_count': len(strokes),
            'zhongshu_low': zhongshu['low'], 'zhongshu_high': zhongshu['high'],
            'signal': signal, 'action': action,
            'entry_price': entry_price, 'stop_loss': stop_loss, 'target_price': target_price,
            'stop_loss_pct': stop_loss_pct, 'target_pct': target_pct,
            'risk_level': risk_level, 'suggestion': suggestion,
            'divergence_info': divergence_info,
            'sell_signal_info': sell_signal_info,
            'signal_score': signal_score.total_score if signal_score else None,
            'signal_grade': signal_score.grade if signal_score else None,
            'signal_probability': signal_score.probability if signal_score else None,
            'sector_info': sector_info  # 新增：板块信息
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


def get_sector_money_flow(days=5):
    """
    获取板块资金净流入数据（过去N个交易日）
    返回：板块名称 -> 净流入金额的字典
    """
    try:
        # 使用Tushare获取行业资金流向
        # 注意：这需要Tushare的pro版权限，如果不可用则返回模拟数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days+5)).strftime('%Y%m%d')
        
        sector_flows = {}
        
        # 尝试获取申万行业资金流向
        try:
            # 获取每日行业涨跌幅作为资金流向的近似
            sw_index = pro.index_classify(level='L1', src='SW2021')
            if sw_index is not None and not sw_index.empty:
                for _, row in sw_index.iterrows():
                    industry_name = row['industry_name']
                    index_code = row['index_code']
                    
                    # 获取行业指数近期走势
                    df_index = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
                    if df_index is not None and len(df_index) >= days:
                        # 计算累计涨跌幅作为资金流向近似
                        total_change = df_index['pct_chg'].head(days).sum()
                        sector_flows[industry_name] = total_change
        except:
            pass
        
        # 如果无法获取，使用模拟数据（基于当前热点）
        if not sector_flows:
            # 模拟2026年热点板块资金流向（用于演示）
            mock_flows = {
                "半导体": 12.5, "计算机": 15.2, "通信": 8.7, "电子": 10.3,
                "电力设备": 9.8, "机械设备": 6.5, "汽车": 7.2, "国防军工": 11.1,
                "有色金属": 5.3, "基础化工": 4.2, "石油石化": 3.1,
                "食品饮料": 2.8, "医药生物": 4.5, "家用电器": 3.9,
                "商业航天": 18.5, "人工智能": 22.3, "固态电池": 16.8,
                "银行": -1.2, "房地产": -2.5, "非银金融": 1.8
            }
            sector_flows = mock_flows
        
        return sector_flows
    except Exception as e:
        return {}


def get_stocks_by_sector_group(group_name):
    """
    根据SECTOR_GROUPS获取指定主线的所有股票
    """
    if group_name not in SECTOR_GROUPS:
        return []
    
    sectors = SECTOR_GROUPS[group_name]["sectors"]
    all_stocks = []
    
    for sector in sectors:
        stocks = get_concept_stocks(sector)
        if stocks:
            all_stocks.extend(stocks)
    
    # 去重
    seen = set()
    unique_stocks = []
    for symbol, name in all_stocks:
        if symbol not in seen:
            seen.add(symbol)
            unique_stocks.append((symbol, name))
    
    return unique_stocks


def filter_stocks_by_money_flow(stock_list, sector_flows, top_n=10):
    """
    筛选资金净流入前N的板块中的股票
    """
    if not sector_flows or not stock_list:
        return stock_list
    
    # 获取资金净流入前N的板块
    top_sectors = sorted(sector_flows.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_sector_names = [s[0] for s in top_sectors]
    
    # 获取这些板块的所有股票
    hot_stocks = []
    for sector_name in top_sector_names:
        sector_stocks = get_concept_stocks(sector_name)
        if sector_stocks:
            hot_stocks.extend(sector_stocks)
    
    # 取交集：用户选择的股票池 ∩ 热门板块股票
    hot_symbols = set([s[0] for s in hot_stocks])
    filtered = [(s[0], s[1]) for s in stock_list if s[0] in hot_symbols]
    
    return filtered if filtered else stock_list  # 如果交集为空，返回原列表


def get_top_volume_stocks(n=100):
    """
    获取全A股成交额前N名的股票
    优先使用efinance或akshare，否则使用Tushare备选
    """
    try:
        if REALTIME_DATA_SOURCE == "efinance":
            # 使用efinance获取当日行情
            df = ef.stock.get_realtime_quotes()
            if df is not None and not df.empty:
                # 按成交额排序
                df['成交额'] = pd.to_numeric(df['成交额'], errors='coerce')
                df = df.sort_values('成交额', ascending=False).head(n)
                stocks = []
                for _, row in df.iterrows():
                    code = row['股票代码']
                    name = row['股票名称']
                    stocks.append((code, name))
                return stocks
                
        elif REALTIME_DATA_SOURCE == "akshare":
            # 使用akshare获取当日行情
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                # 按成交额排序（akshare列名可能不同）
                if '成交额' in df.columns:
                    df = df.sort_values('成交额', ascending=False).head(n)
                elif '成交量' in df.columns:
                    df = df.sort_values('成交量', ascending=False).head(n)
                else:
                    return []
                
                stocks = []
                for _, row in df.iterrows():
                    code = row['代码']
                    name = row['名称']
                    stocks.append((code, name))
                return stocks
        
        # 备选：使用Tushare获取昨日数据（可能非实时）
        # 获取当日所有股票行情
        df = pro.daily_basic(trade_date=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'),
                             fields='ts_code,name,amount')
        if df is not None and not df.empty:
            df = df.sort_values('amount', ascending=False).head(n)
            stocks = []
            for _, row in df.iterrows():
                code = row['ts_code'].split('.')[0]
                name = row['name']
                stocks.append((code, name))
            return stocks
            
    except Exception as e:
        print(f"获取成交额前{n}失败: {e}")
    
    return []


def get_stock_sector_info(symbol):
    """
    获取股票所属板块及资金流向信息
    返回: {
        'sectors': ['板块1', '板块2'],
        'sector_flow': {'板块1': 5.2, '板块2': -1.3},  # 5日资金净流入百分比
        'main_sector': '主要板块'
    }
    """
    try:
        # 使用Tushare获取股票所属行业
        info = pro.stock_company(ts_code=f"{symbol}.SH" if symbol.startswith('6') else f"{symbol}.SZ")
        if info is None or info.empty:
            return None
        
        # 获取行业分类
        industry = info.iloc[0].get('industry', '')
        
        # 获取该行业近5日资金流向（使用模拟数据或真实数据）
        sector_flows = get_sector_money_flow(days=5)
        
        sectors = [industry] if industry else []
        
        # 计算主要板块的资金流向
        sector_flow = {}
        for sector in sectors:
            if sector in sector_flows:
                sector_flow[sector] = sector_flows[sector]
        
        # 找出主要板块（资金流入最多的）
        main_sector = max(sector_flow.items(), key=lambda x: x[1])[0] if sector_flow else sectors[0] if sectors else ''
        
        return {
            'sectors': sectors,
            'sector_flow': sector_flow,
            'main_sector': main_sector,
            'main_sector_flow': sector_flow.get(main_sector, 0)
        }
        
    except Exception as e:
        print(f"获取{symbol}板块信息失败: {e}")
        return None


def merge_with_top_volume(selected_stocks, top_n=100):
    """
    将精选股票与成交额前N名合并
    """
    # 获取成交额前N
    top_stocks = get_top_volume_stocks(top_n)
    
    # 合并并去重（精选股票优先）
    seen = set([s[0] for s in selected_stocks])
    merged = list(selected_stocks)  # 先放精选股票
    
    for code, name in top_stocks:
        if code not in seen:
            seen.add(code)
            merged.append((code, name))
    
    return merged


def get_selected_stocks(pool_name):
    """
    获取2026核心赛道精选股票池
    """
    if pool_name not in SELECTED_STOCKS:
        return []
    
    pool = SELECTED_STOCKS[pool_name]
    stocks = list(zip(pool["codes"], pool["names"]))
    return stocks


def get_all_selected_stocks():
    """
    获取所有精选股票（去重）
    """
    all_stocks = []
    seen = set()
    
    for pool_name, pool_data in SELECTED_STOCKS.items():
        for code, name in zip(pool_data["codes"], pool_data["names"]):
            if code not in seen:
                seen.add(code)
                all_stocks.append((code, name))
    
    return all_stocks


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
        ["自定义股票池", "2026核心赛道精选", "板块自动扫描"],
        help="选择自定义股票池手动输入股票，或选择精选赛道/板块自动获取成分股"
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
        
    elif pool_mode == "2026核心赛道精选":
        st.sidebar.markdown("---")
        st.sidebar.subheader("⭐ 2026核心赛道精选")
        
        # 精选股票池选择
        selected_pool = st.sidebar.selectbox(
            "选择精选赛道",
            list(SELECTED_STOCKS.keys()),
            format_func=lambda x: f"{x} - {SELECTED_STOCKS[x]['description']}"
        )
        
        # 显示该赛道的股票
        if selected_pool:
            st.sidebar.caption(f"**包含股票：**")
            for code, name in zip(SELECTED_STOCKS[selected_pool]["codes"], 
                                  SELECTED_STOCKS[selected_pool]["names"]):
                st.sidebar.markdown(f"• **{code}** {name}")
        
        # 新增：合并成交额前100选项
        merge_top_volume = st.sidebar.checkbox("🔥 合并成交额前100", value=True,
            help="将精选股票与当日成交额前100名合并，捕捉市场热点")
        
        if st.sidebar.button("🔄 加载精选股票"):
            stocks = get_selected_stocks(selected_pool)
            
            # 如果启用合并
            if merge_top_volume:
                with st.spinner("正在获取成交额前100..."):
                    stocks = merge_with_top_volume(stocks, top_n=100)
                    st.sidebar.success(f"已加载精选股票 + 成交额前100，共 {len(stocks)} 只")
            else:
                st.sidebar.success(f"已加载 {len(stocks)} 只精选股票")
            
            if stocks:
                st.session_state['concept_stocks'] = stocks
        
        # 一键加载全部精选（也支持合并）
        if st.sidebar.button("📊 加载全部25只"):
            all_stocks = get_all_selected_stocks()
            
            # 如果启用合并
            if merge_top_volume:
                with st.spinner("正在获取成交额前100..."):
                    all_stocks = merge_with_top_volume(all_stocks, top_n=100)
                    st.sidebar.success(f"已加载全部精选 + 成交额前100，共 {len(all_stocks)} 只")
            else:
                st.sidebar.success(f"已加载全部 {len(all_stocks)} 只精选股票")
            
            st.session_state['concept_stocks'] = all_stocks
        
        if 'concept_stocks' in st.session_state:
            stock_list = st.session_state['concept_stocks']
            st.sidebar.info(f"当前: {len(stock_list)} 只精选股票")
        else:
            stock_list = []
    
    else:
        st.sidebar.markdown("---")
        st.sidebar.subheader("🔍 2026热点主线扫描")
        
        # 使用新的SECTOR_GROUPS配置
        group_options = list(SECTOR_GROUPS.keys())
        selected_group = st.sidebar.selectbox(
            "选择投资主线",
            group_options,
            format_func=lambda x: f"{x} - {SECTOR_GROUPS[x]['description']}"
        )
        
        # 显示该主线包含的板块
        if selected_group:
            st.sidebar.caption(f"包含板块: {', '.join(SECTOR_GROUPS[selected_group]['sectors'][:6])}...")
            st.sidebar.caption(f"评分加权: {SECTOR_GROUPS[selected_group]['weight']}x")
        
        # 资金流向筛选选项
        use_money_flow = st.sidebar.checkbox("💰 启用资金流向筛选", value=True, 
            help="优先筛选资金净流入前10板块的股票")
        
        if st.sidebar.button("🔄 获取成分股"):
            with st.spinner(f"正在获取 {selected_group} 主线股票..."):
                # 获取主线所有股票
                group_stocks = get_stocks_by_sector_group(selected_group)
                
                if group_stocks:
                    # 如果启用资金流向筛选
                    if use_money_flow:
                        with st.spinner("获取板块资金流向..."):
                            sector_flows = get_sector_money_flow(days=5)
                            if sector_flows:
                                filtered_stocks = filter_stocks_by_money_flow(group_stocks, sector_flows, top_n=10)
                                # 显示资金流向信息
                                top_sectors = sorted(sector_flows.items(), key=lambda x: x[1], reverse=True)[:5]
                                flow_info = " | ".join([f"{s[0]}({s[1]:+.1f}%)" for s in top_sectors])
                                st.sidebar.success(f"资金流向TOP5: {flow_info}")
                                
                                if len(filtered_stocks) < len(group_stocks):
                                    st.sidebar.info(f"资金流向筛选: 从 {len(group_stocks)} 只筛选至 {len(filtered_stocks)} 只")
                                
                                st.session_state['concept_stocks'] = filtered_stocks
                            else:
                                st.session_state['concept_stocks'] = group_stocks
                    else:
                        st.session_state['concept_stocks'] = group_stocks
                    
                    st.sidebar.success(f"获取到 {len(st.session_state['concept_stocks'])} 只成分股")
                else:
                    st.sidebar.error("未找到该主线成分股")
        
        if 'concept_stocks' in st.session_state:
            stock_list = st.session_state['concept_stocks']
            st.sidebar.info(f"当前主线: {len(stock_list)} 只股票")
    
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
        
        # 统计 - 分类显示各种信号（包含评分和二买）
        # 原有信号分类
        buy3_all = [r for r in results if '三买' in r['signal'] and '评分' in r['signal']]
        buy3_high = [r for r in results if '三买' in r['signal'] and r.get('signal_grade') in ['A', 'B']]
        buy3_low = [r for r in results if '三买' in r['signal'] and r.get('signal_grade') in ['C', 'D']]
        buy3_div = [r for r in results if r['signal'] == '三买+背驰']
        
        # 二买分类：区分板块资金流入为正的情况
        buy2_strong = [r for r in results if r['signal'] == '强力二买']
        buy2_standard = [r for r in results if r['signal'] == '标准二买']
        
        # 重点：二买 + 板块资金流入为正
        buy2_strong_hot = [r for r in buy2_strong if r.get('sector_info') and r['sector_info'].get('main_sector_flow', 0) > 0]
        buy2_standard_hot = [r for r in buy2_standard if r.get('sector_info') and r['sector_info'].get('main_sector_flow', 0) > 0]
        
        buy1 = [r for r in results if r['signal'] == '一买']
        buy1_div = [r for r in results if r['signal'] == '一买+背驰']
        sell3 = [r for r in results if '三卖' in r['signal']]
        sell2 = [r for r in results if r['signal'] == '二卖']
        
        # 显示统计卡片
        st.subheader("📊 信号统计（含二买板块资金流向）")
        
        # 买入信号行 - 优先显示二买+板块资金流入
        cols = st.columns(4)
        cols[0].metric("📊 分析股票", len(results))
        cols[1].metric("🔥 二买+资金流入", len(buy2_strong_hot) + len(buy2_standard_hot), delta="优先关注")
        cols[2].metric("💪 强力二买", len(buy2_strong), delta="核心买点")
        cols[3].metric("📐 标准二买", len(buy2_standard), delta="有效买点")
        
        # 卖出信号行
        cols2 = st.columns(4)
        cols2[0].metric("⚠️ 三卖信号", len(sell3), delta="卖出")
        cols2[1].metric("🚀 三买(A/B级)", len(buy3_high), delta="强势突破")
        cols2[2].metric("⚡ 二卖信号", len(sell2), delta="减仓")
        cols2[3].metric("❌ 无信号", len(results) - len(buy3_all) - len(buy1) - len(buy3_div) - len(sell3) - len(sell2) - len(buy2_strong) - len(buy2_standard))
        
        # 显示资金流向说明
        with st.expander("📖 资金流向说明"):
            st.markdown("""
            **二买信号筛选逻辑：**
            - **🔥 二买+板块资金流入**: 二买信号且所属板块5日资金净流入为正（优先展示）
            - **💪 强力二买**: 回抽不破中枢上沿
            - **📐 标准二买**: 回抽进入中枢但未破一买低点
            
            **板块资金流向**：基于5个交易日板块指数涨跌幅计算
            """)
        
        st.markdown("---")
        
        # ===== 优先展示：二买 + 板块资金流入为正 =====
        if buy2_strong_hot or buy2_standard_hot:
            st.subheader("🔥 二买+板块资金流入 - 最强买点（优先关注）")
            st.caption("二买信号确认 + 所属板块5日资金净流入为正，双重确认")
            
            for idx, r in enumerate(buy2_strong_hot + buy2_standard_hot):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        if r['signal'] == '强力二买':
                            st.success("强力二买", icon="💪")
                        else:
                            st.info("标准二买", icon="📐")
                    
                    # 显示板块信息
                    if r.get('sector_info'):
                        sector_name = r['sector_info'].get('main_sector', '未知')
                        sector_flow = r['sector_info'].get('main_sector_flow', 0)
                        flow_emoji = "🟢" if sector_flow > 0 else "🔴"
                        st.success(f"{flow_emoji} 所属板块: {sector_name} | 5日资金: {sector_flow:+.1f}%", icon="📊")
                    
                    # 买卖点
                    if r.get('entry_price'):
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"💰 买入: ¥{r['entry_price']:.2f}")
                        if r.get('stop_loss'):
                            c2.caption(f"🛑 止损: ¥{r['stop_loss']:.1f} ({r['stop_loss_pct']:+.0f}%)")
                        if r.get('target_price'):
                            c3.caption(f"🎯 目标: ¥{r['target_price']:.1f} (+{r['target_pct']:.0f}%)")
                    
                    if r.get('suggestion'):
                        st.success(r['suggestion'])
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        btn_key = f"w_buy2hot_{r['code']}_{idx}"
                        if st.button("⭐ 自选", key=btn_key):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 三卖信号股票（风险警示）
        if sell3:
            st.subheader("⚠️ 三卖信号 - 强势卖出")
            st.caption("向下离开中枢后反弹未回中枢，趋势可能继续下跌")
            for idx, r in enumerate(sell3):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.error("卖出", icon="⚠️")
                    
                    # 显示背驰/卖出信号说明
                    if r.get('sell_signal_info'):
                        st.info(r['sell_signal_info'], icon="📉")
                    
                    # 买卖点
                    if r.get('entry_price'):
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"💰 当前: ¥{r['price']:.2f}")
                        if r.get('stop_loss'):
                            c2.caption(f"🛑 止损: ¥{r['stop_loss']:.1f}")
                        if r.get('target_price'):
                            c3.caption(f"🎯 目标: ¥{r['target_price']:.1f} ({r['target_pct']:+.0f}%)")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_sell3_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 二卖信号股票
        if sell2:
            st.subheader("⚡ 二卖信号 - 减仓")
            st.caption("突破后回抽至中枢内，建议减仓")
            for idx, r in enumerate(sell2):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.warning("减仓", icon="⚡")
                    
                    if r.get('sell_signal_info'):
                        st.info(r['sell_signal_info'], icon="📉")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_sell2_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # ===== 其他二买信号（板块资金未确认或未知）=====
        # 强力二买（板块资金未确认）
        buy2_strong_other = [r for r in buy2_strong if r not in buy2_strong_hot]
        if buy2_strong_other:
            st.subheader("💪 强力二买 - 核心买点（板块资金待确认）")
            st.caption("回抽不破中枢上沿 + 底分型 + MACD衰竭")
            for idx, r in enumerate(buy2_strong_other):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.success("买入", icon="💪")
                    
                    # 显示板块信息（如果有）
                    if r.get('sector_info'):
                        sector_name = r['sector_info'].get('main_sector', '未知')
                        sector_flow = r['sector_info'].get('main_sector_flow', 0)
                        if sector_flow != 0:
                            flow_emoji = "🟢" if sector_flow > 0 else "🔴"
                            st.info(f"{flow_emoji} 所属板块: {sector_name} | 5日资金: {sector_flow:+.1f}%", icon="📊")
                    
                    # 买卖点
                    if r.get('entry_price'):
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"💰 买入: ¥{r['entry_price']:.2f}")
                        if r.get('stop_loss'):
                            c2.caption(f"🛑 止损: ¥{r['stop_loss']:.1f} ({r['stop_loss_pct']:+.0f}%)")
                        if r.get('target_price'):
                            c3.caption(f"🎯 目标: ¥{r['target_price']:.1f} (+{r['target_pct']:.0f}%)")
                    
                    if r.get('suggestion'):
                        st.success(r['suggestion'], icon="📊")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_buy2s_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 标准二买（板块资金未确认）
        buy2_standard_other = [r for r in buy2_standard if r not in buy2_standard_hot]
        if buy2_standard_other:
            st.subheader("📐 标准二买 - 有效买点（板块资金待确认）")
            st.caption("回抽进入中枢但未破一买低点 + 底分型 + MACD衰竭")
            for idx, r in enumerate(buy2_standard_other):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.info("买入", icon="📐")
                    
                    # 显示板块信息（如果有）
                    if r.get('sector_info'):
                        sector_name = r['sector_info'].get('main_sector', '未知')
                        sector_flow = r['sector_info'].get('main_sector_flow', 0)
                        if sector_flow != 0:
                            flow_emoji = "🟢" if sector_flow > 0 else "🔴"
                            st.info(f"{flow_emoji} 所属板块: {sector_name} | 5日资金: {sector_flow:+.1f}%", icon="📊")
                    
                    # 买卖点
                    if r.get('entry_price'):
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"💰 买入: ¥{r['entry_price']:.2f}")
                        if r.get('stop_loss'):
                            c2.caption(f"🛑 止损: ¥{r['stop_loss']:.1f} ({r['stop_loss_pct']:+.0f}%)")
                        if r.get('target_price'):
                            c3.caption(f"🎯 目标: ¥{r['target_price']:.1f} (+{r['target_pct']:.0f}%)")
                    
                    if r.get('suggestion'):
                        st.info(r['suggestion'], icon="💡")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_buy2st_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 三买+背驰信号（特殊处理）
        if buy3_div:
            st.subheader("🎯 三买+背驰 - 谨慎追涨")
            st.caption("价格创新高但力度减弱，建议减仓而非加仓")
            for idx, r in enumerate(buy3_div):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.warning("减仓", icon="⚠️")
                    
                    if r.get('divergence_info'):
                        st.warning(r['divergence_info'], icon="📊")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_buy3div_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 三买信号股票（正常）- 只显示高评分信号
        if buy3_high:
            st.subheader("🎯 三买信号 - 强势突破（A/B级）")
            for idx, r in enumerate(buy3_high):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.success("买入", icon="🚀")
                    
                    # 买卖点
                    if r.get('entry_price'):
                        c1, c2, c3 = st.columns(3)
                        c1.caption(f"💰 买入: ¥{r['entry_price']:.2f}")
                        if r.get('stop_loss'):
                            c2.caption(f"🛑 止损: ¥{r['stop_loss']:.1f} ({r['stop_loss_pct']:+.0f}%)")
                        if r.get('target_price'):
                            c3.caption(f"🎯 目标: ¥{r['target_price']:.1f} (+{r['target_pct']:.0f}%)")
                    
                    if r.get('suggestion'):
                        st.caption(f"💡 {r['suggestion']}")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_buy3_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 一买+背驰信号（加强版一买）
        if buy1_div:
            st.subheader("✨ 一买+背驰 - 底部确认")
            st.caption("底背驰确认，反弹概率高，优于普通一买")
            for idx, r in enumerate(buy1_div):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.success("买入", icon="✨")
                    
                    if r.get('divergence_info'):
                        st.success(r['divergence_info'], icon="📊")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_buy1div_{r['code']}_{idx}"):
                            add_to_watchlist(r['code'], r['name'])
                            st.rerun()
                    st.divider()
        
        # 一买信号股票（普通）
        if buy1:
            st.subheader("📉 一买信号 - 底部反转")
            for idx, r in enumerate(buy1):
                with st.container():
                    cols = st.columns([4, 1])
                    with cols[0]:
                        price_color = "🔴" if r['change'] > 0 else "🟢"
                        st.markdown(f"**{r['code']} {r['name']}** {price_color} ¥{r['price']:.2f} ({r['change']:+.1f}%)")
                    with cols[1]:
                        st.warning("关注", icon="📉")
                    
                    if r.get('suggestion'):
                        st.caption(f"💡 {r['suggestion']}")
                    
                    watchlist = load_watchlist()
                    if any(w['code'] == r['code'] for w in watchlist):
                        st.caption("✅ 已自选")
                    else:
                        if st.button("⭐ 自选", key=f"w_buy1_{r['code']}_{idx}"):
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
            has_buy_signal = any('三买' in r.get('signal', '') or r.get('signal') == '一买' for r in results)
            if has_buy_signal:
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
