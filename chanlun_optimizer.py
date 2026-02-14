# -*- coding: utf-8 -*-
"""
缠论算法优化模块 - 深度重构版
针对二买/三买区分评分，优化形态和量能判断
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
    缠论算法优化器 - 深度重构版
    """
    
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
        买入信号评分 - 深度重构版（人性化调整）
        """
        score = 0
        details = []
        
        if signal_type == '二买':
            # ==================== 二买评分逻辑（人性化重构）====================
            
            # 1. 回踩不破前低 (25分) - 核心条件
            current_price = context.get('current_price', 0)
            first_buy_low = context.get('first_buy_low', current_price)
            
            if current_price > 0 and first_buy_low > 0:
                safety_margin = (current_price - first_buy_low) / first_buy_low * 100
                if safety_margin >= 3:
                    score += 25
                    details.append(f"✓ 回踩不破前低，安全垫{safety_margin:.1f}%(25分)")
                elif safety_margin >= 1:
                    score += 20
                    details.append(f"△ 回踩不破前低，安全垫{safety_margin:.1f}%(20分)")
                else:
                    score += 10
                    details.append(f"⚠ 接近前低，安全垫不足(10分)")
            
            # 2. 缩量评分 (20分) - 二买核心：缩量=抛压枯竭=高分
            vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
            if vol_ratio < 0.7:
                score += 20
                details.append(f"✓ 明显缩量({vol_ratio:.2f}倍)，抛压枯竭(20分)")
            elif vol_ratio < 1.0:
                score += 18
                details.append(f"✓ 轻度缩量({vol_ratio:.2f}倍)，抛压减轻(18分)")
            elif vol_ratio < 1.3:
                score += 10
                details.append(f"○ 成交量正常({vol_ratio:.2f}倍)(10分)")
            else:
                score += 3
                details.append(f"✗ 放量下跌({vol_ratio:.2f}倍)，风险未除(3分)")
            
            # 3. 形态确认分 (25分)
            if context.get('is_standard_pattern', False):
                score += 25
                details.append("✓ 标准向下一笔完成(25分)")
            elif context.get('has_pullback_structure', False):
                score += 15
                details.append("△ 有回抽结构(15分)")
            else:
                details.append("✗ 形态不完整(0分)")
            
            # 4. 底分型额外奖励 (15分) - 实战触发信号
            if context.get('has_bottom_fractal', False):
                score += 15
                details.append("✨ 底分型确认，额外奖励(15分)")
            
            # 5. 盈亏比评估 (10分)
            stop_loss = context.get('stop_loss_price', current_price * 0.95)
            target_price = context.get('target_price', current_price * 1.1)
            
            if current_price > 0:
                risk = (current_price - stop_loss) / current_price * 100
                reward = (target_price - current_price) / current_price * 100
                if risk > 0:
                    rr_ratio = reward / risk
                    if rr_ratio >= 2:
                        score += 10
                        details.append(f"✓ 盈亏比{rr_ratio:.1f}:1优秀(10分)")
                    elif rr_ratio >= 1.5:
                        score += 7
                        details.append(f"△ 盈亏比{rr_ratio:.1f}:1良好(7分)")
                    else:
                        score += 3
                        details.append(f"⚠ 盈亏比{rr_ratio:.1f}:1一般(3分)")
            
            # 6. 市场环境 (5分)
            trend = context.get('market_trend', 'neutral')
            if trend == 'bull':
                score += 5
                details.append("✓ 牛市环境(5分)")
            elif trend == 'neutral':
                score += 3
                details.append("○ 震荡市(3分)")
            else:
                details.append("✗ 熊市环境(0分)")
        
        else:  # 三买
            # ==================== 三买评分逻辑 ====================
            
            # 1. 突破幅度评分 (30分)
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
            
            # 2. 成交量评分 (20分) - 三买需要放量
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
                details.append(f"✗ 缩量({vol_ratio:.2f}倍)，突破存疑(3分)")
            
            # 3. 形态确认分 (25分)
            if context.get('is_standard_pattern', False):
                score += 25
                details.append("✓ 标准向上离开+回踩(25分)")
            elif context.get('has_breakout_structure', False):
                score += 15
                details.append("△ 有突破结构(15分)")
            else:
                score += 8
                details.append("⚠ 形态一般(8分)")
            
            # 4. 次级别确认 (10分)
            if context.get('sublevel_confirm', False):
                score += 10
                details.append("✓ 次级别共振(10分)")
            
            # 5. 盈亏比评估 (10分)
            distance_to_max = context.get('distance_to_max', 50)
            if distance_to_max > 30:
                score += 10
                details.append("✓ 上涨空间充足(10分)")
            elif distance_to_max > 15:
                score += 6
                details.append("△ 上涨空间一般(6分)")
            else:
                score += 2
                details.append("⚠ 接近前高(2分)")
            
            # 6. 市场环境 (5分)
            trend = context.get('market_trend', 'neutral')
            if trend == 'bull':
                score += 5
                details.append("✓ 牛市环境(5分)")
            elif trend == 'neutral':
                score += 3
                details.append("○ 震荡市(3分)")
            else:
                details.append("✗ 熊市环境(0分)")
        
        # ==================== 评级标准（大幅放宽）====================
        if score >= 75:  # A级门槛从85降至75
            grade = "A"
            action = "强烈推荐-重仓买入"
            prob = 0.75
        elif score >= 60:  # B级门槛从70降至60
            grade = "B"
            action = "推荐-适量买入"
            prob = 0.62
        elif score >= 45:  # C级门槛从55降至45
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
            details.append("△ 成交量正常(12分)")
        else:
            details.append("✗ 缩量下跌(0分)")
        
        trend = context.get('market_trend', 'neutral')
        if trend == 'bear':
            score += 15
            details.append("✓ 熊市环境(15分)")
        elif trend == 'neutral':
            score += 8
            details.append("○ 震荡市(8分)")
        else:
            details.append("✗ 牛市环境(0分)")
        
        if context.get('sublevel_confirm'):
            score += 10
            details.append("✓ 次级别确认(10分)")
        
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


# 使用示例
def example_usage():
    """使用示例 - 展示二买评分"""
    optimizer = ChanLunOptimizer()
    
    # 二买示例
    context_2nd_buy = {
        'current_price': 15.5,
        'first_buy_low': 14.8,
        'current_vol': 800000,
        'ma20_vol': 1000000,
        'is_standard_pattern': True,
        'has_bottom_fractal': True,
        'stop_loss_price': 14.5,
        'target_price': 17.0,
        'market_trend': 'bull'
    }
    
    score = optimizer.score_buy_signal(context_2nd_buy, signal_type='二买')
    print("=" * 60)
    print("二买信号评分示例（人性化调整）")
    print("=" * 60)
    print(f"评级: {score.grade}级")
    print(f"总分: {score.total_score}分")
    print(f"建议: {score.action}")
    print(f"预估成功率: {score.probability*100:.0f}%")
    print("\n评分详情:")
    for detail in score.details:
        print(f"  {detail}")


if __name__ == '__main__':
    example_usage()
