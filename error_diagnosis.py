#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缠论系统错误自动诊断与修复建议模块
针对常见错误类型（IndexError、KeyError、ModuleNotFoundError）进行自动分析

用法:
    from error_diagnosis import diagnose_error, suggest_fix
    
    error_msg = "IndexError: index 10 is out of bounds for axis 0 with size 5"
    diagnosis = diagnose_error(error_msg)
    fix = suggest_fix(diagnosis)
"""

import re
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ErrorDiagnosis:
    """错误诊断结果"""
    error_type: str
    severity: str  # critical, high, medium, low
    description: str
    likely_cause: str
    file_hint: Optional[str] = None
    line_hint: Optional[int] = None


@dataclass
class FixSuggestion:
    """修复建议"""
    priority: int  # 1-10, 越高越优先
    description: str
    code_example: str
    files_to_check: List[str]


class ErrorDiagnoser:
    """错误诊断器"""
    
    # 缠论系统中常见的错误模式
    ERROR_PATTERNS = {
        # IndexError 模式
        r"IndexError.*out of bounds.*axis.*size": {
            "type": "IndexError",
            "severity": "high",
            "description": "数组/列表索引越界",
            "likely_cause": "numpy/pandas 切片操作时索引超出范围",
            "common_locations": [
                "handle_inclusion() - K线包含处理",
                "find_strokes() - 找笔函数", 
                "calculate_macd() - MACD计算",
                "check_divergence() - 背驰判断"
            ]
        },
        
        r"IndexError.*list index out of range": {
            "type": "IndexError",
            "severity": "high", 
            "description": "列表索引越界",
            "likely_cause": "访问strokes列表时索引超出范围",
            "common_locations": [
                "find_strokes() - 笔列表访问",
                "analyze_stock() - 信号判断"
            ]
        },
        
        # KeyError 模式
        r"KeyError.*'pinyin'": {
            "type": "KeyError",
            "severity": "medium",
            "description": "DataFrame缺少pinyin列",
            "likely_cause": "get_all_stocks()未正确添加拼音列",
            "common_locations": [
                "search_stocks() - 搜索函数",
                "get_all_stocks() - 股票列表获取"
            ]
        },
        
        r"KeyError.*'(high|low|close|open)'": {
            "type": "KeyError", 
            "severity": "medium",
            "description": "DataFrame缺少价格列",
            "likely_cause": "列名大小写不匹配或数据未正确加载",
            "common_locations": [
                "handle_inclusion() - K线处理",
                "calculate_zhongshu() - 中枢计算"
            ]
        },
        
        # ModuleNotFoundError 模式
        r"ModuleNotFoundError.*chanlun_optimizer": {
            "type": "ModuleNotFoundError",
            "severity": "critical",
            "description": "找不到chanlun_optimizer模块",
            "likely_cause": "模块文件未提交到GitHub",
            "common_locations": [
                "app.py - import语句"
            ]
        },
        
        r"ModuleNotFoundError.*(pandas|numpy|tushare)": {
            "type": "ModuleNotFoundError",
            "severity": "critical",
            "description": "缺少核心依赖包",
            "likely_cause": "requirements.txt未包含该依赖",
            "common_locations": [
                "requirements.txt"
            ]
        },
        
        # AttributeError 模式
        r"AttributeError.*'NoneType'.*has no": {
            "type": "AttributeError",
            "severity": "high",
            "description": "空对象调用方法",
            "likely_cause": "函数返回None但继续调用方法",
            "common_locations": [
                "get_daily() - 数据获取",
                "analyze_stock() - 分析结果处理"
            ]
        },
        
        # ValueError 模式
        r"ValueError.*Length mismatch": {
            "type": "ValueError",
            "severity": "medium",
            "description": "数据长度不匹配",
            "likely_cause": "DataFrame拼接时列数不一致",
            "common_locations": [
                "数据预处理部分"
            ]
        }
    }
    
    @classmethod
    def diagnose(cls, error_message: str, traceback: str = "") -> ErrorDiagnosis:
        """
        诊断错误类型
        
        Args:
            error_message: 错误信息文本
            traceback: 完整的堆栈跟踪（可选）
            
        Returns:
            ErrorDiagnosis 对象
        """
        error_message = error_message.strip()
        
        # 匹配错误模式
        for pattern, info in cls.ERROR_PATTERNS.items():
            if re.search(pattern, error_message, re.IGNORECASE):
                # 尝试从traceback中提取文件和行号
                file_hint, line_hint = cls._extract_location(traceback)
                
                return ErrorDiagnosis(
                    error_type=info["type"],
                    severity=info["severity"],
                    description=info["description"],
                    likely_cause=info["likely_cause"],
                    file_hint=file_hint,
                    line_hint=line_hint
                )
        
        # 未知错误类型
        return ErrorDiagnosis(
            error_type="Unknown",
            severity="medium",
            description="未识别的错误类型",
            likely_cause="需要人工分析",
            file_hint=None,
            line_hint=None
        )
    
    @classmethod
    def _extract_location(cls, traceback: str) -> tuple:
        """从traceback中提取文件路径和行号"""
        if not traceback:
            return None, None
            
        # 匹配 File "path", line X
        pattern = r'File "([^"]+)", line (\d+)'
        matches = re.findall(pattern, traceback)
        
        if matches:
            # 返回最后一个匹配（通常是用户代码）
            return matches[-1][0], int(matches[-1][1])
        
        return None, None


class FixSuggester:
    """修复建议生成器"""
    
    FIX_TEMPLATES = {
        "IndexError": {
            "bounds_check": {
                "priority": 10,
                "description": "添加数组边界检查",
                "code_example": '''
# 优化前（容易出错）
last_stroke = strokes[-1]

# 优化后（安全检查）
if len(strokes) > 0:
    last_stroke = strokes[-1]
else:
    return None  # 或适当处理

# 对于索引访问
if idx < len(strokes):
    stroke = strokes[idx]
else:
    logger.warning(f"索引{idx}超出范围，列表长度{len(strokes)}")
    return None
                ''',
                "files_to_check": ["app.py"]
            },
            "dataframe_slicing": {
                "priority": 9,
                "description": "DataFrame切片前检查长度",
                "code_example": '''
# 优化前
df_processed = handle_inclusion(df.reset_index(drop=True))
strokes = find_strokes(df_processed)

# 优化后
if len(df) < 5:  # 最小数据要求
    logger.warning(f"[{symbol}] 数据不足: {len(df)} 天")
    return None

df_processed = handle_inclusion(df.reset_index(drop=True))
if df_processed.empty:
    return None
    
strokes = find_strokes(df_processed)
if len(strokes) < 2:  # 至少需要2笔
    return None
                ''',
                "files_to_check": ["app.py", "chanlun_optimizer.py"]
            }
        },
        
        "KeyError": {
            "column_check": {
                "priority": 8,
                "description": "添加列存在性检查",
                "code_example": '''
# 优化前
pinyin_match = stock_df[stock_df['pinyin'].str.startswith(query)]

# 优化后
if 'pinyin' not in stock_df.columns:
    # 重新计算拼音列
    stock_df['pinyin'] = stock_df['name'].apply(
        lambda x: ''.join(lazy_pinyin(x, style=Style.FIRST_LETTER)).upper()
    )

pinyin_match = stock_df[stock_df['pinyin'].str.startswith(query, na=False)]
                ''',
                "files_to_check": ["app.py", "data_source.py"]
            }
        },
        
        "ModuleNotFoundError": {
            "add_requirements": {
                "priority": 10,
                "description": "添加缺失的依赖到requirements.txt",
                "code_example": '''
# requirements.txt
pydantic>=2.0.0
pydantic-settings>=2.0.0
tenacity>=8.2.0
# 如果使用了新模块，确保添加
# chanlun_optimizer.py 不需要单独添加，因为它在同一目录
                ''',
                "files_to_check": ["requirements.txt"]
            },
            "git_add": {
                "priority": 10,
                "description": "确保所有.py文件已提交",
                "code_example": '''
# 执行命令
git add chanlun_optimizer.py
git commit -m "Add missing module"
git push origin master
                ''',
                "files_to_check": [".git"]
            }
        }
    }
    
    @classmethod
    def suggest(cls, diagnosis: ErrorDiagnosis) -> List[FixSuggestion]:
        """
        根据诊断结果生成修复建议
        
        Args:
            diagnosis: 错误诊断结果
            
        Returns:
            FixSuggestion 列表（按优先级排序）
        """
        suggestions = []
        
        if diagnosis.error_type == "IndexError":
            # IndexError 主要修复方案
            suggestions.append(cls.FIX_TEMPLATES["IndexError"]["bounds_check"])
            suggestions.append(cls.FIX_TEMPLATES["IndexError"]["dataframe_slicing"])
            
        elif diagnosis.error_type == "KeyError":
            # KeyError 主要修复方案
            suggestions.append(cls.FIX_TEMPLATES["KeyError"]["column_check"])
            
        elif diagnosis.error_type == "ModuleNotFoundError":
            # ModuleNotFoundError 主要修复方案
            suggestions.append(cls.FIX_TEMPLATES["ModuleNotFoundError"]["add_requirements"])
            suggestions.append(cls.FIX_TEMPLATES["ModuleNotFoundError"]["git_add"])
        
        # 转换为 FixSuggestion 对象
        result = []
        for key, template in suggestions:
            if isinstance(template, dict):
                result.append(FixSuggestion(
                    priority=template["priority"],
                    description=template["description"],
                    code_example=template["code_example"],
                    files_to_check=template["files_to_check"]
                ))
        
        # 按优先级排序
        result.sort(key=lambda x: x.priority, reverse=True)
        return result


def diagnose_error(error_message: str, traceback: str = "") -> str:
    """
    便捷函数：诊断错误并返回可读报告
    
    用法:
        report = diagnose_error(error_msg, traceback)
        print(report)
    """
    diagnosis = ErrorDiagnoser.diagnose(error_message, traceback)
    suggestions = FixSuggester.suggest(diagnosis)
    
    report = []
    report.append("=" * 80)
    report.append("🔍 错误诊断报告")
    report.append("=" * 80)
    report.append(f"错误类型: {diagnosis.error_type}")
    report.append(f"严重程度: {diagnosis.severity}")
    report.append(f"问题描述: {diagnosis.description}")
    report.append(f"可能原因: {diagnosis.likely_cause}")
    
    if diagnosis.file_hint:
        report.append(f"问题位置: {diagnosis.file_hint}:{diagnosis.line_hint}")
    
    report.append("")
    report.append("=" * 80)
    report.append("🔧 修复建议（按优先级排序）")
    report.append("=" * 80)
    
    for i, sug in enumerate(suggestions, 1):
        report.append(f"\n{i}. [优先级{ sug.priority}] {sug.description}")
        report.append(f"   需要检查的文件: {', '.join(sug.files_to_check)}")
        report.append(f"   代码示例:")
        for line in sug.code_example.strip().split('\n'):
            report.append(f"   {line}")
    
    report.append("")
    report.append("=" * 80)
    
    return "\n".join(report)


# 便捷函数
def quick_fix_indexerror(file_path: str, line_num: int, context: str = "") -> str:
    """
    快速生成 IndexError 修复代码
    """
    return f''"
# 在 {file_path}:{line_num} 附近添加边界检查

# 如果访问列表/数组
if index < len(your_list):
    value = your_list[index]
else:
    logger.warning(f"索引越界: {index} >= {len(your_list)}")
    {context if context else "return None  # 或适当处理"}

# 如果访问DataFrame
if len(df) > required_min_rows:
    result = df.iloc[index]
else:
    logger.warning(f"数据不足: {len(df)} rows")
    return None
"""


if __name__ == "__main__":
    # 测试用例
    test_errors = [
        "IndexError: index 10 is out of bounds for axis 0 with size 5",
        "KeyError: 'pinyin'",
        "ModuleNotFoundError: No module named 'chanlun_optimizer'",
    ]
    
    for err in test_errors:
        print(diagnose_error(err))
        print("\n" + "="*80 + "\n")
