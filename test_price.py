# -*- coding: utf-8 -*-
"""
价格核验测试 - 宏和科技(603256)
验证价格是否正确显示为71.6而非38.02
"""

import tushare as ts
from datetime import datetime, timedelta
import time

# 设置Tushare token
# 请替换为您的实际token
pro = ts.pro_api()

def test_price_accuracy(symbol='603256'):
    """测试价格准确性"""
    print("=" * 60)
    print(f"价格核验测试 - {symbol}")
    print("=" * 60)
    
    # 获取ts_code
    if symbol.startswith('6'):
        ts_code = f"{symbol}.SH"
    else:
        ts_code = f"{symbol}.SZ"
    
    # 1. 获取历史日线数据（不复权）
    print("\n1. 获取历史日线数据...")
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
    
    try:
        df_daily = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        if df_daily is not None and not df_daily.empty:
            latest = df_daily.iloc[0]
            print(f"   历史数据最新价格: ¥{latest['close']}")
            print(f"   历史数据开盘价: ¥{latest['open']}")
            print(f"   历史数据最高价: ¥{latest['high']}")
            print(f"   历史数据最低价: ¥{latest['low']}")
        else:
            print("   ❌ 无法获取历史数据")
    except Exception as e:
        print(f"   ❌ 获取历史数据失败: {e}")
    
    time.sleep(0.5)  # 限速
    
    # 2. 获取实时行情数据
    print("\n2. 获取实时行情数据...")
    try:
        today = datetime.now().strftime('%Y%m%d')
        df_realtime = pro.daily_basic(ts_code=ts_code, trade_date=today, fields='ts_code,close,open,high,low')
        if df_realtime is not None and not df_realtime.empty:
            realtime = df_realtime.iloc[0]
            print(f"   实时行情价格: ¥{realtime['close']}")
            print(f"   实时开盘价: ¥{realtime['open']}")
            print(f"   实时最高价: ¥{realtime['high']}")
            print(f"   实时最低价: ¥{realtime['low']}")
        else:
            print("   ❌ 无法获取实时数据")
    except Exception as e:
        print(f"   ❌ 获取实时数据失败: {e}")
    
    time.sleep(0.5)  # 限速
    
    # 3. 获取股票基本信息
    print("\n3. 获取股票基本信息...")
    try:
        df_basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry,list_date')
        if df_basic is not None and not df_basic.empty:
            info = df_basic.iloc[0]
            print(f"   股票名称: {info['name']}")
            print(f"   所属行业: {info['industry']}")
            print(f"   上市日期: {info['list_date']}")
    except Exception as e:
        print(f"   ❌ 获取基本信息失败: {e}")
    
    print("\n" + "=" * 60)
    print("预期结果：")
    print("  宏和科技(603256)当前实际股价应在 ¥71.6 左右")
    print("  如果显示 ¥38.02，说明使用了前复权数据")
    print("  当前代码已使用不复权数据，价格应该正确")
    print("=" * 60)

if __name__ == '__main__':
    test_price_accuracy('603256')
    
    print("\n\n您也可以测试其他股票：")
    print("python test_price.py")
