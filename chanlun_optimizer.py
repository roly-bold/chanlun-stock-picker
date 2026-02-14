# -*- coding: utf-8 -*-
"""
缠论算法优化模块 - 重构版
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
    缠论算法优化器 - 重构版
    """
    
    def __init__(self):
        self.volatility_cache = {}
    
    # ==================== 1. 动态阈值系统 ====================
    
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
        """判断突破是否有效（基于动态阈值）"""
        if signal_type == '三买':
            if breakout_pct < threshold['三买_min']:
                return False, f"突破幅度{breakout_pct:.1f}%不足（最低{threshold['三买_min']}%）"
            elif breakout_pct > threshold['三买_max']:
                return False, f"突破幅度{breakout_pct:.1f}%过大（最高{threshold['三买_max']}%），追高风险"
            else:
                return True, f"突破幅度{breakout_pct:.1f}%在合理区间"
        
        elif signal_type == '三卖':
            if breakout_pct < threshold['三卖_min']:
                return False, f"跌破幅度{breakout_pct:.1f}%不足"
            else:
                return True, f"跌破幅度{breakout_pct:.1f}%有效"
        
        return True, ""
    
    # ==================== 2. 重构的信号评分系统 ====================
    
    def score_buy_signal(self, context: Dict, signal_type: str = '三买') -> SignalScore:
        """
        买入信号评分 - 重构版
        
        Args:
            context: {
                # 通用参数
                'current_vol': 当前成交量,
                'ma20_vol': 20日均量,
                'market_trend': 市场环境,
                
                # 三买专用
                'breakout_pct': 突破幅度,
                'distance_to_max': 距离历史高点,
                
                # 二买专用（新增）
                'pullback_depth': 回踩深度(%),  # 相对于反弹高点的回踩
                'first_buy_low': 一买最低点价格,
                'current_price': 当前价格,
                'stop_loss_price': 止损价格,
                
                # 形态判断（新增）
                'is_standard_pattern': 是否标准形态（向下一笔+底分型）,
                'has_bottom_fractal': 是否有底分型,
                
                # 次级别
                'sublevel_confirm': 次级别确认
            }
            signal_type: '三买' 或 '二买'
        """
        score = 0
        details = []
        
        if signal_type == '二买':
            # ==================== 二买评分逻辑 ====================
            
            # 1. 回踩深度评分 (30分) - 替代突破幅度
            # 二买看回踩：回踩不创新低且缩量是买点
            pullback = context.get('pullback_depth', 30)  # 默认30%回踩
            
            if pullback <= 30:  # 回踩较浅（强势）
                score += 30
                details.append(f"✓ 回踩较浅({pullback:.1f}%)，强势二买(30分)")
            elif pullback <= 50:  # 正常回踩
                score += 25
                details.append(f"△ 正常回踩({pullback:.1f}%)，标准二买(25分)")
            elif pullback <= 70:  # 回踩较深
                score += 15
                details.append(f"⚠ 回踩较深({pullback:.1f}%)，偏弱(15分)")
            else:  # 回踩过深，可能失败
                score += 5
                details.append(f"✗ 回踩过深({pullback:.1f}%)，风险高(5分)")
            
            # 2. 缩量判断 (20分) - 反转逻辑：缩量给高分
            vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
            if vol_ratio < 0.7:  # 明显缩量（卖盘衰竭）
                score += 20
                details.append("✓ 明显缩量，卖盘衰竭(20分)")
            elif vol_ratio < 1.0:  # 轻度缩量
                score += 15
                details.append("△ 轻度缩量，抛压减轻(15分)")
            elif vol_ratio < 1.3:  # 成交量正常
                score += 10
                details.append("○ 成交量正常(10分)")
            else:  # 放量下跌（危险）
                details.append("✗ 放量下跌，卖压沉重(0分)")
            
            # 3. 形态分 (30分) - 新增
            if context.get('is_standard_pattern', False):
                score += 30
                details.append("✓ 标准向下一笔+底分型，形态完美(30分)")
            elif context.get('has_bottom_fractal', False):
                score += 20
                details.append("△ 有底分型，形态良好(20分)")
            else:
                details.append("✗ 形态不标准，无底分型(0分)")
            
            # 4. 盈亏比评估 (10分) - 替代距离历史高点
            current_price = context.get('current_price', 0)
            stop_loss = context.get('stop_loss_price', current_price * 0.95)
            
            if current_price > 0:
                risk_pct = (current_price - stop_loss) / current_price * 100
                if risk_pct < 3:  # 止损空间小，盈亏比好
                    score += 10
                    details.append(f"✓ 止损空间小({risk_pct:.1f}%)，盈亏比优(10分)")
                elif risk_pct < 5:
                    score += 6
                    details.append(f"△ 止损适中({risk_pct:.1f}%)，盈亏比良(6分)")
                else:
                    details.append(f"⚠ 止损空间大({risk_pct:.1f}%)，盈亏比一般(0分)")
            else:
                details.append("○ 无法计算盈亏比(0分)")
            
            # 5. 市场环境 (10分)
            trend = context.get('market_trend', 'neutral')
            if trend == 'bull':
                score += 10
                details.append("✓ 牛市环境(10分)")
            elif trend == 'neutral':
                score += 5
                details.append("○ 震荡市(5分)")
            else:
                details.append("✗ 熊市环境(0分)")
            
            # 6. 次级别确认 (加分项，不扣分)
            if context.get('sublevel_confirm') == True:
                score += 5
                details.append("✓ 次级别共振确认(+5分)")
        
        else:  # 三买
            # ==================== 三买评分逻辑（保留并优化） ====================
            
            # 1. 突破幅度评分 (30分) - 放宽至12%以前均为良好
            breakout = context.get('breakout_pct', 0)
            if 3 <= breakout <= 8:
                score += 30
                details.append(f"✓ 突破幅度{breakout:.1f}%理想(30分)")
            elif 8 <= breakout <= 12:  # 放宽至12%
                score += 25  # 仍给高分
                details.append(f"△ 突破幅度{breakout:.1f}%良好(25分)")
            elif 12 <= breakout <= 15:
                score += 15
                details.append(f"⚠ 突破幅度{breakout:.1f}%偏高(15分)")
            else:
                score += 5
                details.append(f"✗ 突破幅度{breakout:.1f}%偏差(5分)")
            
            # 2. 成交量判断 (20分) - 三买需要放量
            vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
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
            
            # 3. 形态分 (30分)
            if context.get('is_standard_pattern', False):
                score += 30
                details.append("✓ 标准向上离开+回踩确认，形态完美(30分)")
            else:
                details.append("△ 形态一般(15分)")
                score += 15
            
            # 4. 盈亏比评估 (10分)
            distance = context.get('distance_to_max', 50)
            if distance > 30:
                score += 10
                details.append("✓ 上涨空间大(10分)")
            elif distance > 15:
                score += 5
                details.append("△ 上涨空间中等(5分)")
            else:
                details.append("✗ 接近历史高点(0分)")
            
            # 5. 市场环境 (10分)
            trend = context.get('market_trend', 'neutral')
            if trend == 'bull':
                score += 10
                details.append("✓ 牛市环境(10分)")
            elif trend == 'neutral':
                score += 5
                details.append("○ 震荡市(5分)")
            else:
                details.append("✗ 熊市环境(0分)")
            
            # 6. 次级别确认
            if context.get('sublevel_confirm') == True:
                score += 5
                details.append("✓ 次级别确认(+5分)")
        
        # ==================== 评级标准（降低门槛） ====================
        # B级降至60分，C级降至45分
        if score >= 80:
            grade = "A"
            action = "强烈推荐-重仓买入"
            prob = 0.75
        elif score >= 60:  # 降低B级门槛
            grade = "B"
            action = "推荐-适量买入"
            prob = 0.60
        elif score >= 45:  # 降低C级门槛
            grade = "C"
            action = "谨慎-小仓位试探"
            prob = 0.45
        elif score >= 30:
            grade = "D"
            action = "观望-等待确认"
            prob = 0.30
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
        """卖出信号评分（三卖/二卖）- 保持原逻辑"""
        score = 0
        details = []
        
        # 1. 跌破幅度 (30分)
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
        
        # 2. 回抽确认 (25分)
        rebound = context.get('rebound_pct', 0)
        if rebound < 1:
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
        
        # 3. 成交量 (20分)
        vol_ratio = context.get('current_vol', 0) / max(context.get('ma20_vol', 1), 1)
        if vol_ratio > 1.5:
            score += 20
            details.append("✓ 放量下跌(20分)")
        elif vol_ratio > 1.0:
            score += 12
            details.append("△ 成交量正常(12分)")
        else:
            details.append("✗ 缩量下跌(0分)")
        
        # 4. 市场环境 (15分)
        trend = context.get('market_trend', 'neutral')
        if trend == 'bear':
            score += 15
            details.append("✓ 熊市环境(15分)")
        elif trend == 'neutral':
            score += 8
            details.append("○ 震荡市(8分)")
        else:
            details.append("✗ 牛市环境(0分)")
        
        # 5. 次级别确认 (10分)
        if context.get('sublevel_confirm'):
            score += 10
            details.append("✓ 次级别确认(10分)")
        
        # 评级（同样降低门槛）
        if score >= 80:
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
        """检查次级别确认（简化版框架）"""
        if signal_type in ['三买', '二买']:
            return False, "次级别数据暂不可用"
        elif signal_type in ['三卖', '二卖']:
            return False, "次级别数据暂不可用"
        
        return False, "未知信号类型"


# ==================== 使用示例 ====================

def example_usage():
    """使用示例 - 展示二买评分"""
    optimizer = ChanLunOptimizer()
    
    # 示例：二买评分
    context_2nd_buy = {
        'signal_type': '二买',
        'pullback_depth': 35,  # 35%回踩
        'current_vol': 800000,  # 缩量
        'ma20_vol': 1000000,
        'current_price': 15.5,
        'stop_loss_price': 14.8,
        'is_standard_pattern': True,  # 标准形态
        'has_bottom_fractal': True,
        'market_trend': 'bull',
        'sublevel_confirm': True
    }
    
    score = optimizer.score_buy_signal(context_2nd_buy, signal_type='二买')
    print("=" * 60)
    print("二买信号评分示例")
    print("=" * 60)
    print(f"评级: {score.grade}级")
    print(f"总分: {score.total_score}分")
    print(f"建议: {score.action}")
    print(f"预估成功率: {score.probability*100:.0f}%")
    print("\n评分详情:")
    for detail in score.details:
        print(f"  {detail}")
    
    # 示例：三买评分
    context_3rd_buy = {
        'signal_type': '三买',
        'breakout_pct': 10,  # 10%突破
        'current_vol': 1800000,  # 放量
        'ma20_vol': 1000000,
        'is_standard_pattern': True,
        'distance_to_max': 40,
        'market_trend': 'bull',
        'sublevel_confirm': False
    }
    
    score3 = optimizer.score_buy_signal(context_3rd_buy, signal_type='三买')
    print("\n" + "=" * 60)
    print("三买信号评分示例")
    print("=" * 60)
    print(f"评级: {score3.grade}级")
    print(f"总分: {score3.total_score}分")
    print(f"建议: {score3.action}")
    print(f"预估成功率: {score3.probability*100:.0f}%")
    print("\n评分详情:")
    for detail in score3.details:
        print(f"  {detail}")


if __name__ == '__main__':
    example_usage()
