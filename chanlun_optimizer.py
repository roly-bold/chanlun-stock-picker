# -*- coding: utf-8 -*-
"""
缠论算法优化模块 - 二买专项优化版
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SignalScore:
    """信号评分结果"""
    total_score: int
    grade: str
    action: str
    probability: float
    details: list


class ChanLunOptimizer:
    """缠论算法优化器 - 二买专项优化版"""
    
    def __init__(self):
        self.volatility_cache = {}
    
    def calculate_atr(self, df: pd.DataFrame, period: int = 20) -> float:
        """计算平均真实波幅(ATR)"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        return atr if not np.isnan(atr) else 0
    
    def get_dynamic_threshold(self, df: pd.DataFrame, code: str = "") -> Dict:
        """根据股票波动率动态调整阈值"""
        atr = self.calculate_atr(df)
        avg_price = df['close'].mean()
        volatility = atr / avg_price if avg_price > 0 else 0.03
        
        if volatility > 0.04:
            return {
                'volatility_level': 'high',
                '三买_max': 25.0,
                '三买_min': 3.0,
                '三卖_min': 2.0,
                'description': '高波动股'
            }
        elif volatility > 0.025:
            return {
                'volatility_level': 'medium',
                '三买_max': 15.0,
                '三买_min': 2.0,
                '三卖_min': 2.0,
                'description': '中波动股'
            }
        else:
            return {
                'volatility_level': 'low',
                '三买_max': 10.0,
                '三买_min': 1.0,
                '三卖_min': 1.5,
                'description': '低波动股'
            }
    
    def is_valid_breakout(self, breakout_pct: float, threshold: Dict, signal_type: str) -> Tuple[bool, str]:
        """判断突破是否有效"""
        if signal_type == '三买':
            if breakout_pct < threshold['三买_min']:
                return False, f"突破幅度{breakout_pct:.1f}%不足"
            elif breakout_pct > threshold['三买_max']:
                return False, f"突破幅度{breakout_pct:.1f}%过大，追高风险"
            else:
                return True, f"突破幅度{breakout_pct:.1f}%合理"
        
        elif signal_type == '三卖':
            if breakout_pct < threshold['三卖_min']:
                return False, f"跌破幅度{breakout_pct:.1f}%不足"
            else:
                return True, f"跌破幅度{breakout_pct:.1f}%有效"
        
        return True, ""
    
    def score_buy_signal(self, context: Dict, signal_type: str = '三买') -> SignalScore:
        """
        买入信号评分 - 二买专项优化版
        """
        score = 0
        details = []
        
        if signal_type == '二买':
            # ==================== 二买专属评分逻辑（专项优化）====================
            
            # 1. 【核心】回踩不破底 - 基础分40分
            current_price = context.get('current_price', 0)
            first_buy_low = context.get('first_buy_low', current_price)
            
            if current_price > 0 and first_buy_low > 0:
                if current_price > first_buy_low:
                    # 只要不破一买最低点，直接给40分基础分
                    score += 40
                    safety_margin = (current_price - first_buy_low) / first_buy_low * 100
                    details.append(f"✓✓ 回踩不破底，基础分(40分)")
                else:
                    # 破底了，不给分
                    details.append(f"✗✗ 跌破一买低点，二买不成立(0分)")
            
            # 2. 【缩量奖励】缩量即给20分
            vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
            if vol_ratio < 1.0:
                score += 20
                details.append(f"✓✓ 缩量回踩({vol_ratio:.2f}倍<1.0)，奖励(20分)")
            else:
                details.append(f"△ 未明显缩量({vol_ratio:.2f}倍)")
            
            # 3. 【形态确认】底分型奖励20分
            if context.get('has_bottom_fractal', False):
                score += 20
                details.append(f"✓✓ 底分型确认，奖励(20分)")
            else:
                details.append(f"△ 无底分型确认")
            
            # 4. 盈亏比评估 (10分)
            stop_loss = context.get('stop_loss_price', first_buy_low * 0.98)
            target_price = context.get('target_price', current_price * 1.1)
            
            if current_price > 0 and stop_loss > 0:
                risk = (current_price - stop_loss) / current_price * 100
                reward = (target_price - current_price) / current_price * 100
                if risk > 0:
                    rr_ratio = reward / risk
                    if rr_ratio >= 2:
                        score += 10
                        details.append(f"✓ 盈亏比优秀(10分)")
                    elif rr_ratio >= 1.5:
                        score += 5
                        details.append(f"△ 盈亏比一般(5分)")
            
            # 5. 市场环境 (5分)
            trend = context.get('market_trend', 'neutral')
            if trend == 'bull':
                score += 5
                details.append("✓ 牛市(5分)")
            elif trend == 'neutral':
                score += 3
                details.append("○ 震荡(3分)")
            
            # 6. 次级别确认 (加分项)
            if context.get('sublevel_confirm', False):
                score += 5
                details.append("✨ 次级别确认(+5分)")
        
        else:  # 三买
            # ==================== 三买评分逻辑 ====================
            
            # 1. 突破幅度评分 (30分)
            breakout = context.get('breakout_pct', 0)
            if 3 <= breakout <= 8:
                score += 30
                details.append(f"✓ 突破{breakout:.1f}%理想(30分)")
            elif 8 <= breakout <= 12:
                score += 25
                details.append(f"△ 突破{breakout:.1f}%良好(25分)")
            elif 12 <= breakout <= 15:
                score += 15
                details.append(f"⚠ 突破{breakout:.1f}%偏高(15分)")
            else:
                score += 5
                details.append(f"✗ 突破{breakout:.1f}%偏差(5分)")
            
            # 2. 成交量评分 (20分)
            vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
            if vol_ratio > 2.0:
                score += 20
                details.append(f"✓ 大幅放量({vol_ratio:.2f}倍)(20分)")
            elif vol_ratio > 1.5:
                score += 16
                details.append(f"△ 明显放量({vol_ratio:.2f}倍)(16分)")
            elif vol_ratio > 1.0:
                score += 10
                details.append(f"○ 正常放量({vol_ratio:.2f}倍)(10分)")
            else:
                score += 3
                details.append(f"✗ 缩量({vol_ratio:.2f}倍)(3分)")
            
            # 3. 形态确认分 (25分)
            if context.get('is_standard_pattern', False):
                score += 25
                details.append("✓ 标准形态(25分)")
            elif context.get('has_breakout_structure', False):
                score += 15
                details.append("△ 有结构(15分)")
            else:
                score += 8
                details.append("⚠ 形态一般(8分)")
            
            # 4. 次级别确认 (10分)
            if context.get('sublevel_confirm', False):
                score += 10
                details.append("✓ 次级别(10分)")
            
            # 5. 盈亏比评估 (10分)
            distance_to_max = context.get('distance_to_max', 50)
            if distance_to_max > 30:
                score += 10
                details.append("✓ 空间大(10分)")
            elif distance_to_max > 15:
                score += 6
                details.append("△ 空间一般(6分)")
            else:
                score += 2
                details.append("⚠ 接近前高(2分)")
            
            # 6. 市场环境 (5分)
            trend = context.get('market_trend', 'neutral')
            if trend == 'bull':
                score += 5
                details.append("✓ 牛市(5分)")
            elif trend == 'neutral':
                score += 3
                details.append("○ 震荡(3分)")
        
        # ==================== 最终级联评分（门槛已放宽）====================
        # A级: 75分, B级: 60分, C级: 45分
        if score >= 75:
            grade = "A"
            action = "强烈推荐-重仓买入"
            prob = 0.75
        elif score >= 60:
            grade = "B"
            action = "推荐-适量买入"
            prob = 0.62
        elif score >= 45:
            grade = "C"
            action = "谨慎-小仓位试探"
            prob = 0.48
        elif score >= 30:
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
        """卖出信号评分"""
        score = 0
        details = []
        
        breakout = abs(context.get('breakout_pct', 0))
        if breakout > 5:
            score += 30
            details.append(f"✓ 强势跌破(30分)")
        elif breakout > 3:
            score += 25
            details.append(f"△ 有效跌破(25分)")
        elif breakout > 1.5:
            score += 15
            details.append(f"○ 跌破(15分)")
        else:
            score += 8
            details.append(f"⚠ 微弱跌破(8分)")
        
        rebound = context.get('rebound_pct', 0)
        if rebound < 1:
            score += 25
            details.append("✓ 回抽极弱(25分)")
        elif rebound < 2:
            score += 20
            details.append("△ 回抽较弱(20分)")
        elif rebound < 5:
            score += 10
            details.append("○ 回抽正常(10分)")
        else:
            details.append("✗ 回抽过强(0分)")
        
        vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
        if vol_ratio > 1.5:
            score += 20
            details.append("✓ 放量下跌(20分)")
        elif vol_ratio > 1.0:
            score += 12
            details.append("△ 正常(12分)")
        else:
            details.append("✗ 缩量(0分)")
        
        trend = context.get('market_trend', 'neutral')
        if trend == 'bear':
            score += 15
            details.append("✓ 熊市(15分)")
        elif trend == 'neutral':
            score += 8
            details.append("○ 震荡(8分)")
        else:
            details.append("✗ 牛市(0分)")
        
        if context.get('sublevel_confirm'):
            score += 10
            details.append("✓ 次级别(10分)")
        
        if score >= 75:
            grade = "A"
            action = "强烈推荐-立即卖出"
            prob = 0.75
        elif score >= 60:
            grade = "B"
            action = "推荐-减仓"
            prob = 0.62
        elif score >= 45:
            grade = "C"
            action = "谨慎-部分减仓"
            prob = 0.48
        elif score >= 30:
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
    
    def check_sublevel_confirm(self, code: str, signal_type: str, 
                               daily_zhongshu: Dict, daily_price: float) -> Tuple[bool, str]:
        """检查次级别确认"""
        if signal_type in ['三买', '二买']:
            return False, "次级别数据暂不可用"
        elif signal_type in ['三卖', '二卖']:
            return False, "次级别数据暂不可用"
        
        return False, "未知信号类型"
