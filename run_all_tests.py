#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缠论系统完整测试套件
整合自动化测试 + 错误诊断

用法:
    # 快速测试
    python run_all_tests.py
    
    # 完整测试（含截图）
    python run_all_tests.py --full
    
    # 指定URL测试
    python run_all_tests.py --url https://your-app.streamlit.app
    
    # 仅诊断已有错误
    python run_all_tests.py --diagnose-only
"""

import argparse
import sys
import asyncio
from datetime import datetime

# 导入测试模块
from test_chanlun_auto import ChanLunTester, quick_test
from error_diagnosis import diagnose_error


def run_diagnosis_only():
    """仅运行错误诊断（用于已有错误日志的情况）"""
    print("=" * 80)
    print("🔍 缠论系统错误诊断模式")
    print("=" * 80)
    
    # 常见错误模式示例
    common_errors = [
        {
            "name": "IndexError - 数组越界",
            "error": "IndexError: index 10 is out of bounds for axis 0 with size 5",
            "traceback": '''
File "/app/chanlun_optimizer.py", line 45, in calculate_atr
    return tr.rolling(window=period).mean().iloc[-1]
IndexError: index -1 is out of bounds for axis 0 with size 0
            '''
        },
        {
            "name": "KeyError - 缺少pinyin列", 
            "error": "KeyError: 'pinyin'",
            "traceback": '''
File "/app/app.py", line 384, in search_stocks
    pinyin_match = stock_df[stock_df['pinyin'].str.startswith(query)]
KeyError: 'pinyin'
            '''
        },
        {
            "name": "ModuleNotFoundError - 缺少模块",
            "error": "ModuleNotFoundError: No module named 'chanlun_optimizer'",
            "traceback": '''
File "/app/app.py", line 25, in <module>
    from chanlun_optimizer import ChanLunOptimizer
ModuleNotFoundError: No module named 'chanlun_optimizer'
            '''
        }
    ]
    
    print("\n请选择要诊断的错误类型（或输入自定义错误）:")
    for i, err in enumerate(common_errors, 1):
        print(f"  {i}. {err['name']}")
    print("  4. 输入自定义错误")
    print("  5. 退出")
    
    try:
        choice = input("\n选择 [1-5]: ").strip()
        
        if choice == "5":
            return
        elif choice == "4":
            error_msg = input("请输入错误信息: ").strip()
            traceback = input("请输入堆栈跟踪（可选，直接回车跳过）: ").strip()
            print("\n" + diagnose_error(error_msg, traceback))
        elif choice in ["1", "2", "3"]:
            err = common_errors[int(choice)-1]
            print(f"\n诊断: {err['name']}")
            print("=" * 80)
            print(diagnose_error(err['error'], err['traceback']))
        else:
            print("无效选择")
            
    except KeyboardInterrupt:
        print("\n\n已取消")
    except Exception as e:
        print(f"诊断失败: {e}")


def run_full_test_suite(url: str, headless: bool = True) -> bool:
    """运行完整测试套件"""
    print("=" * 80)
    print("🧪 缠论系统完整测试套件")
    print("=" * 80)
    print(f"测试地址: {url}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 运行测试
    tester = ChanLunTester(url=url, headless=headless)
    result = asyncio.run(tester.run_full_test())
    
    # 如果有错误，自动诊断
    if result["errors"]:
        print("\n" + "=" * 80)
        print("🔍 自动错误诊断")
        print("=" * 80)
        
        for i, error in enumerate(result["errors"][:3], 1):  # 只诊断前3个错误
            print(f"\n错误 {i}:")
            print(diagnose_error(error))
    
    # 返回测试结果
    return result["fail"] == 0 and len(result["errors"]) == 0


def main():
    parser = argparse.ArgumentParser(
        description="缠论选股系统测试与诊断工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 快速测试本地服务
  python run_all_tests.py
  
  # 完整测试（含截图）
  python run_all_tests.py --full
  
  # 测试线上服务
  python run_all_tests.py --url https://your-app.streamlit.app --full
  
  # 仅诊断错误（无需启动浏览器）
  python run_all_tests.py --diagnose-only
        """
    )
    
    parser.add_argument("--url", default="http://localhost:8501",
                       help="测试地址 (默认: http://localhost:8501)")
    parser.add_argument("--full", action="store_true",
                       help="运行完整测试（含截图和详细检查）")
    parser.add_argument("--visible", action="store_true",
                       help="显示浏览器窗口（调试用）")
    parser.add_argument("--diagnose-only", action="store_true",
                       help="仅运行错误诊断，不启动浏览器测试")
    
    args = parser.parse_args()
    
    # 模式选择
    if args.diagnose_only:
        run_diagnosis_only()
        return
    
    if args.full:
        success = run_full_test_suite(args.url, headless=not args.visible)
    else:
        # 快速测试
        print("🚀 快速测试模式")
        print(f"测试地址: {args.url}")
        success = asyncio.run(quick_test(args.url))
    
    # 退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
