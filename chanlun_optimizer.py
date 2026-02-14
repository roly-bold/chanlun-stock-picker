# -*- coding: utf-8 -*-
"""
缠论算法优化模块 - 可直接集成到app.py
包含：动态阈值、递归确认、信号评分
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SignalScore:
    """信号评分结果"""
    total_score: int
    grade: str  # A/B/C/D
    action: str
    probability: float
    details: list


class ChanLunOptimizer:
    """
    缠论算法优化器
    
    使用方式:
        optimizer = ChanLunOptimizer()
        
        # 1. 动态阈值判断
        threshold = optimizer.get_dynamic_threshold(df)
        
        # 2. 信号评分
        score = optimizer.score_buy_signal(context)
        
        # 3. 递归确认
        confirmed = optimizer.check_sublevel_confirm(code, '三买')
    """
    
    def __init__(self):
        self.volatility_cache = {}
    
    # ==================== 1. 动态阈值系统 ====================
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 20) -> float:
        """
        计算平均真实波幅(ATR)
        
        ATR = 平均真实波幅，衡量股票波动性
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        # 真实波幅 = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        return atr if not np.isnan(atr) else 0
    
    def get_dynamic_threshold(self, df: pd.DataFrame, code: str = "") -> Dict:
        """
        根据股票波动率动态调整阈值
        
        Returns:
            {
                '三买_max': 最大突破幅度,
                '三买_min': 最小突破幅度,
                '三卖_min': 最小跌破幅度
            }
        """
        # 计算波动率
        atr = self.calculate_atr(df)
        avg_price = df['close'].mean()
        volatility = atr / avg_price if avg_price > 0 else 0.03
        
        # 根据波动率分级
        if volatility > 0.04:  # 高波动（新能源、半导体等）
            return {
                'volatility_level': 'high',
                '三买_max': 25.0,      # 放宽上限
                '三买_min': 3.0,       # 提高下限
                '三卖_min': 2.0,
                'description': '高波动股'
            }
        elif volatility > 0.025:  # 中波动（消费、医药等）
            return {
                'volatility_level': 'medium',
                '三买_max': 15.0,
                '三买_min': 2.0,
                '三卖_min': 2.0,
                'description': '中波动股'
            }
        else:  # 低波动（银行、基建等）
            return {
                'volatility_level': 'low',
                '三买_max': 10.0,      # 收紧上限
                '三买_min': 1.0,       # 降低下限
                '三卖_min': 1.5,
                'description': '低波动股'
            }
    
    def is_valid_breakout(self, breakout_pct: float, threshold: Dict, signal_type: str) -> Tuple[bool, str]:
        """
        判断突破是否有效（基于动态阈值）
        
        Args:
            breakout_pct: 突破/跌破幅度(%)
            threshold: 动态阈值
            signal_type: '三买' 或 '三卖'
            
        Returns:
            (是否有效, 原因说明)
        """
        if signal_type == '三买':
            if breakout_pct < threshold['三买_min']:
                return False, f"突破幅度{breakout_pct:.1f}%不足（最低{threshold['三买_min']}%）"
            elif breakout_pct > threshold['三买_max']:
                return False, f"突破幅度{breakout_pct:.1f}%过大（最高{threshold['三买_max']}%），追高风险"
            else:
                return True, f"突破幅度{breakout_pct:.1f}%在合理区间"
        
        elif signal_type == '三卖':
            # 三卖：跌破幅度越大越好
            if breakout_pct < threshold['三卖_min']:
                return False, f"跌破幅度{breakout_pct:.1f}%不足"
            else:
                return True, f"跌破幅度{breakout_pct:.1f}%有效"
        
        return True, ""
    
    # ==================== 2. 信号评分系统 ====================
    
    def score_buy_signal(self, context: Dict) -> SignalScore:
        """
        买入信号评分（三买/二买）
        
        Args:
            context: {
                'breakout_pct': 突破幅度,
                'current_vol': 当前成交量,
                'ma20_vol': 20日均量,
                'sublevel_confirm': 次级别确认(bool),
                'market_trend': 市场环境('bull'/'neutral'/'bear'),
                'distance_to_max': 距离历史高点(%)
            }
        """
        score = 0
        details = []
        
        # 1. 突破幅度评分 (0-30分)
        breakout = context.get('breakout_pct', 0)
        if 3 <= breakout <= 8:
            score += 30
            details.append(f"✓ 突破幅度{breakout:.1f}%理想(30分)")
        elif 8 <= breakout <= 12:
            score += 25
            details.append(f"△ 突破幅度{breakout:.1f}%良好(25分)")
        elif 12 <= breakout <= 15:
            score += 15
            details.append(f"⚠ 突破幅度{breakout:.1f}%偏高(15分)")
        else:
            score += 5
            details.append(f"✗ 突破幅度{breakout:.1f}%偏差(5分)")
        
        # 2. 成交量配合 (0-20分)
        vol_ratio = context.get('current_vol', 0) / context.get('ma20_vol', 1)
        if vol_ratio > 2.0:
            score += 20
            details.append("✓ 成交量大幅放大(20分)")
        elif vol_ratio > 1.5:
            score += 15
            details.append("△ 成交量明显放大(15分)")
        elif vol_ratio > 1.0:
            score += 10
            details.append("○ 成交量正常(10分)")
        else:
            details.append("✗ 成交量萎缩(0分)")
        
        # 3. 次级别确认 (0-25分)
        if context.get('sublevel_confirm') == True:
            score += 25
            details.append("✓ 次级别确认(25分)")
        elif context.get('sublevel_confirm') == 'partial':
            score += 12
            details.append("△ 次级别部分确认(12分)")
        else:
            details.append("✗ 次级别未确认(0分)")
        
        # 4. 市场环境 (0-15分)
        trend = context.get('market_trend', 'neutral')
        if trend == 'bull':
            score += 15
            details.append("✓ 牛市环境(15分)")
        elif trend == 'neutral':
            score += 8
            details.append("○ 震荡市(8分)")
        else:
            details.append("✗ 熊市环境(0分)")
        
        # 5. 位置评估 (0-10分)
        distance = context.get('distance_to_max', 50)
        if distance > 30:  # 距离高点还有30%以上空间
            score += 10
            details.append("✓ 上涨空间大(10分)")
        elif distance > 15:
            score += 5
            details.append("△ 上涨空间中等(5分)")
        else:
            details.append("✗ 接近历史高点(0分)")
        
        # 评级
        if score >= 85:
            grade = "A"
            action = "强烈推荐-重仓买入"
            prob = 0.72
        elif score >= 70:
            grade = "B"
            action = "推荐-适量买入"
            prob = 0.58
        elif score >= 55:
            grade = "C"
            action = "谨慎-小仓位试探"
            prob = 0.45
        elif score >= 40:
            grade = "D"
            action = "观望-等待确认"
            prob = 0.32
        else:
            grade = "E"
            action = "放弃-风险过高"
            prob = 0.18
        
        return SignalScore(
            total_score=score,
            grade=grade,
            action=action,
            probability=prob,
            details=details
        )
    
    def score_sell_signal(self, context: Dict) -> SignalScore:
        """卖出信号评分（三卖/二卖）"""
        score = 0
        details = []
        
        # 1. 跌破幅度 (0-30分)
        breakout = abs(context.get('breakout_pct', 0))
        if breakout > 5:
            score += 30
            details.append(f"✓ 强势跌破{breakout:.1f}%(30分)")
        elif breakout > 3:
            score += 25
            details.append(f"△ 有效跌破{breakout:.1f}%(25分)")
        elif breakout > 1.5:
            score += 15
            details.append(f"○ 跌破{breakout:.1f}%(15分)")
        else:
            score += 8
            details.append(f"⚠ 微弱跌破{breakout:.1f}%(8分)")
        
        # 2. 回抽确认 (0-25分)
        rebound = context.get('rebound_pct', 0)
        if rebound < 1:  # 回抽<1%是强势信号
            score += 25
            details.append("✓ 回抽极弱，趋势强劲(25分)")
        elif rebound < 2:
            score += 20
            details.append("△ 回抽较弱(20分)")
        elif rebound < 5:
            score += 10
            details.append("○ 回抽正常(10分)")
        else:
            details.append("✗ 回抽过强，可能失败(0分)")
        
        # 3. 成交量 (0-20分)
        vol_ratio = context.get('current_vol', 0) / context.get('ma20_vol', 1)
        if vol_ratio > 1.5:
            score += 20
            details.append("✓ 放量下跌(20分)")
        elif vol_ratio > 1.0:
            score += 12
            details.append("△ 成交量正常(12分)")
        else:
            details.append("✗ 缩量下跌(0分)")
        
        # 4. 市场环境 (0-15分)
        trend = context.get('market_trend', 'neutral')
        if trend == 'bear':
            score += 15
            details.append("✓ 熊市环境(15分)")
        elif trend == 'neutral':
            score += 8
            details.append("○ 震荡市(8分)")
        else:
            details.append("✗ 牛市环境(0分)")
        
        # 5. 次级别确认 (0-10分)
        if context.get('sublevel_confirm'):
            score += 10
            details.append("✓ 次级别确认(10分)")
        
        # 评级
        if score >= 80:
            grade = "A"
            action = "强烈推荐-立即卖出"
            prob = 0.75
        elif score >= 65:
            grade = "B"
            action = "推荐-减仓"
            prob = 0.62
        elif score >= 50:
            grade = "C"
            action = "谨慎-部分减仓"
            prob = 0.48
        elif score >= 35:
            grade = "D"
            action = "观望-设置止损"
            prob = 0.35
        else:
            grade = "E"
            action = "持仓-可能假突破"
            prob = 0.22
        
        return SignalScore(
            total_score=score,
            grade=grade,
            action=action,
            probability=prob,
            details=details
        )
    
    # ==================== 3. 递归确认系统 ====================
    
    def check_sublevel_confirm(self, code: str, signal_type: str, 
                               daily_zhongshu: Dict, daily_price: float) -> Tuple[bool, str]:
        """
        检查次级别确认（简化版框架）
        
        实际实现需要接入30分钟/60分钟数据
        
        Returns:
            (是否确认, 确认类型)
        """
        # 这里接入真实的次级别数据检查
        # 简化示意：
        
        if signal_type in ['三买', '二买']:
            # 检查30分钟是否出现二买
            # 实际实现：获取30分钟数据，计算笔和中枢
            return False, "次级别数据暂不可用"
        
        elif signal_type in ['三卖', '二卖']:
            # 检查30分钟是否出现二卖
            return False, "次级别数据暂不可用"
        
        return False, "未知信号类型"


# ==================== 使用示例 ====================

def example_usage():
    """使用示例"""
    optimizer = ChanLunOptimizer()
    
    # 示例1：动态阈值
    df = pd.DataFrame({
        'high': [10, 11, 12, 11, 13, 14, 15],
        'low': [9, 10, 11, 10, 12, 13, 14],
        'close': [9.5, 10.5, 11.5, 10.5, 12.5, 13.5, 14.5]
    })
    
    threshold = optimizer.get_dynamic_threshold(df)
    print(f"动态阈值: {threshold}")
    
    # 示例2：信号评分
    context = {
        'breakout_pct': 7.5,
        'current_vol': 1500000,
        'ma20_vol': 1000000,
        'sublevel_confirm': True,
        'market_trend': 'bull',
        'distance_to_max': 25
    }
    
    score = optimizer.score_buy_signal(context)
    print(f"\n信号评分: {score.grade}级, {score.total_score}分")
    print(f"建议: {score.action}, 成功率{score.probability*100:.0f}%")
    print("评分详情:")
    for detail in score.details:
        print(f"  {detail}")


if __name__ == '__main__':
    example_usage()
