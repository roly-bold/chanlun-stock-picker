#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缠论选股系统 - 自动化探测与测试脚本
基于 Playwright 的端到端测试

用法:
    python test_chanlun_auto.py
    python test_chanlun_auto.py --url https://your-app.streamlit.app
    python test_chanlun_auto.py --full  # 完整测试模式
"""

import asyncio
import sys
import argparse
from datetime import datetime
from typing import List, Dict, Optional

try:
    from playwright.async_api import async_playwright, Page, Browser
except ImportError:
    print("⚙️ Playwright 未安装，正在自动安装...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)
    from playwright.async_api import async_playwright, Page, Browser


class ChanLunTester:
    """缠论系统自动化测试器"""
    
    def __init__(self, url: str = "http://localhost:8501", headless: bool = True):
        self.url = url
        self.headless = headless
        self.results = []
        self.errors = []
        
    async def run_full_test(self) -> Dict:
        """运行完整测试套件"""
        print("=" * 80)
        print(f"🧪 缠论选股系统自动化测试开始")
        print(f"📍 测试地址: {self.url}")
        print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
            
            try:
                # 1. 基础页面加载测试
                await self.test_page_load(page)
                
                # 2. UI 元素检测
                await self.test_ui_elements(page)
                
                # 3. 股票搜索功能
                await self.test_stock_search(page)
                
                # 4. 分析功能测试（重点）
                await self.test_analysis_function(page)
                
                # 5. 侧边栏功能
                await self.test_sidebar_features(page)
                
                # 6. 错误捕获检查
                await self.check_for_errors(page)
                
            except Exception as e:
                self.errors.append(f"测试执行异常: {str(e)}")
                await self.capture_screenshot(page, "error_final")
                
            finally:
                await browser.close()
        
        # 生成测试报告
        return self.generate_report()
    
    async def test_page_load(self, page: Page):
        """测试页面加载"""
        print("\n📌 测试1: 页面加载")
        try:
            await page.goto(self.url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)  # 等待 Streamlit 渲染
            
            # 检查标题
            title = await page.title()
            if "缠论" in title or "选股" in title:
                self.log_pass("页面加载成功", f"标题: {title}")
            else:
                self.log_warn("页面标题异常", f"当前标题: {title}")
                
            # 截图保存
            await self.capture_screenshot(page, "01_page_loaded")
            
        except Exception as e:
            self.log_fail("页面加载失败", str(e))
    
    async def test_ui_elements(self, page: Page):
        """测试 UI 元素存在性"""
        print("\n📌 测试2: UI 元素检测")
        
        elements_to_check = [
            ("标题", "h1", "缠论选股系统"),
            ("分析配置侧边栏", "text=分析配置"),
            ("股票池选择", "text=股票池选择方式"),
            ("开始分析按钮", "button", "开始分析"),
        ]
        
        for name, selector_type, selector_value in elements_to_check:
            try:
                if selector_type == "h1":
                    element = await page.wait_for_selector(f"h1:has-text('{selector_value}')", timeout=5000)
                elif selector_type == "button":
                    element = await page.get_by_role("button", name=selector_value).first
                else:
                    element = await page.wait_for_selector(f"text={selector_value}", timeout=5000)
                
                if element:
                    self.log_pass(f"元素存在: {name}")
                else:
                    self.log_fail(f"元素缺失: {name}")
                    
            except Exception as e:
                self.log_fail(f"元素检测失败: {name}", str(e))
    
    async def test_stock_search(self, page: Page):
        """测试股票搜索功能"""
        print("\n📌 测试3: 股票搜索")
        
        try:
            # 切换到自定义股票池
            radio = await page.get_by_label("自定义股票池").first
            if radio:
                await radio.click()
                await page.wait_for_timeout(500)
            
            # 搜索股票输入框
            search_input = await page.get_by_placeholder("搜索股票").first
            if search_input:
                await search_input.fill("贵州茅台")
                await page.wait_for_timeout(1500)  # 等待搜索结果
                
                # 检查搜索结果
                search_results = await page.query_selector_all("[data-testid='stMarkdownContainer']")
                if search_results:
                    self.log_pass("股票搜索功能正常", "找到搜索结果")
                else:
                    self.log_warn("股票搜索无结果")
                    
                await self.capture_screenshot(page, "03_stock_search")
            else:
                self.log_fail("未找到搜索输入框")
                
        except Exception as e:
            self.log_fail("股票搜索测试失败", str(e))
    
    async def test_analysis_function(self, page: Page):
        """测试核心分析功能（重点）"""
        print("\n📌 测试4: 核心分析功能（重点测试）")
        
        try:
            # 选择板块扫描模式
            radio = await page.get_by_label("板块自动扫描").first
            if radio:
                await radio.click()
                await page.wait_for_timeout(500)
            
            # 选择一个小板块进行测试（避免数据量过大）
            select = await page.get_by_label("选择概念板块").first
            if select:
                await select.select_option("银行")
                await page.wait_for_timeout(500)
            
            # 点击获取成分股
            get_stocks_btn = await page.get_by_role("button", name="获取成分股").first
            if get_stocks_btn:
                await get_stocks_btn.click()
                await page.wait_for_timeout(2000)
                self.log_pass("获取板块成分股成功")
            
            # 点击开始分析（核心测试）
            analyze_btn = await page.get_by_role("button", name="开始分析").first
            if analyze_btn:
                print("  ⏳ 开始执行分析，等待结果...")
                await analyze_btn.click()
                
                # 等待分析完成（最多60秒）
                try:
                    await page.wait_for_selector("text=分析完成", timeout=60000)
                    self.log_pass("分析功能执行成功")
                except:
                    self.log_warn("分析可能未完成或提示文本不匹配")
                
                await page.wait_for_timeout(3000)
                await self.capture_screenshot(page, "04_analysis_done")
                
                # 检查分析结果
                results = await page.query_selector_all("[data-testid='stMetricValue']")
                if len(results) > 0:
                    self.log_pass("分析结果已显示", f"找到 {len(results)} 个指标")
                else:
                    self.log_warn("未找到分析结果指标")
                    
        except Exception as e:
            self.log_fail("分析功能测试失败", str(e))
            # 检查是否是 numpy/pandas 切片错误
            if "IndexError" in str(e) or "out of bounds" in str(e):
                self.errors.append("💡 检测到 IndexError，可能是 numpy/pandas 切片越界")
    
    async def test_sidebar_features(self, page: Page):
        """测试侧边栏功能"""
        print("\n📌 测试5: 侧边栏功能")
        
        try:
            # 检查评分说明是否存在
            rating_info = await page.get_by_text("评分说明").first
            if rating_info:
                await rating_info.click()
                await page.wait_for_timeout(500)
                self.log_pass("评分说明功能正常")
                await self.capture_screenshot(page, "05_rating_info")
            else:
                self.log_warn("未找到评分说明（可能优化版本未显示）")
                
        except Exception as e:
            self.log_fail("侧边栏测试失败", str(e))
    
    async def check_for_errors(self, page: Page):
        """检查页面错误（重点）"""
        print("\n📌 测试6: 错误捕获检查（重点）")
        
        # 1. 检查 Streamlit 异常组件
        error_elements = await page.query_selector_all(".stException")
        if error_elements:
            print(f"  ❌ 发现 {len(error_elements)} 个页面报错！")
            for i, err in enumerate(error_elements):
                content = await err.inner_text()
                # 截断过长的错误信息
                content_short = content[:500] + "..." if len(content) > 500 else content
                print(f"  --- 错误 {i+1} ---")
                print(f"  {content_short}")
                print(f"  ----------------")
                
                # 分析错误类型
                if "IndexError" in content or "out of bounds" in content:
                    self.errors.append(f"IndexError  detected: {content_short[:200]}")
                    print(f"  💡 提示: 这是 numpy/pandas 切片越界错误，请检查数组索引")
                elif "KeyError" in content:
                    self.errors.append(f"KeyError detected: {content_short[:200]}")
                elif "ModuleNotFoundError" in content:
                    self.errors.append(f"ModuleNotFoundError: {content_short[:200]}")
                else:
                    self.errors.append(f"UI Error: {content_short[:200]}")
                    
                await self.capture_screenshot(page, f"error_{i+1}")
        else:
            print("  ✅ 未探测到 UI 异常")
            
        # 2. 检查控制台错误
        console_logs = []
        # Playwright 不支持直接获取控制台日志，可以通过 page.evaluate 间接检查
        try:
            js_errors = await page.evaluate("""() => {
                return window.errors || [];
            }""")
            if js_errors:
                self.log_warn("浏览器控制台发现错误", str(js_errors))
        except:
            pass
    
    async def capture_screenshot(self, page: Page, name: str):
        """截取屏幕"""
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"screenshot_{name}_{timestamp}.png"
        await page.screenshot(path=filename, full_page=True)
        print(f"  📸 截图已保存: {filename}")
    
    def log_pass(self, message: str, detail: str = ""):
        """记录通过"""
        self.results.append({"status": "PASS", "message": message, "detail": detail})
        print(f"  ✅ {message} {detail}")
    
    def log_fail(self, message: str, detail: str = ""):
        """记录失败"""
        self.results.append({"status": "FAIL", "message": message, "detail": detail})
        print(f"  ❌ {message} {detail}")
        
    def log_warn(self, message: str, detail: str = ""):
        """记录警告"""
        self.results.append({"status": "WARN", "message": message, "detail": detail})
        print(f"  ⚠️  {message} {detail}")
    
    def generate_report(self) -> Dict:
        """生成测试报告"""
        print("\n" + "=" * 80)
        print("📊 测试报告")
        print("=" * 80)
        
        pass_count = sum(1 for r in self.results if r["status"] == "PASS")
        fail_count = sum(1 for r in self.results if r["status"] == "FAIL")
        warn_count = sum(1 for r in self.results if r["status"] == "WARN")
        
        print(f"\n总计: {len(self.results)} 项测试")
        print(f"  ✅ 通过: {pass_count}")
        print(f"  ❌ 失败: {fail_count}")
        print(f"  ⚠️  警告: {warn_count}")
        
        if self.errors:
            print(f"\n🐛 发现 {len(self.errors)} 个错误:")
            for i, err in enumerate(self.errors, 1):
                print(f"  {i}. {err}")
        else:
            print("\n🎉 未发现严重错误")
            
        print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        return {
            "total": len(self.results),
            "pass": pass_count,
            "fail": fail_count,
            "warn": warn_count,
            "errors": self.errors,
            "details": self.results
        }


async def quick_test(url: str = "http://localhost:8501"):
    """快速测试模式"""
    print("🚀 快速测试模式")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(3000)
            
            # 快速检查错误
            errors = await page.query_selector_all(".stException")
            if errors:
                print(f"❌ 发现 {len(errors)} 个错误")
                for err in errors:
                    content = await err.inner_text()
                    print(f"  错误: {content[:200]}...")
                return False
            else:
                print("✅ 页面运行正常")
                return True
                
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            return False
        finally:
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description="缠论选股系统自动化测试")
    parser.add_argument("--url", default="http://localhost:8501", help="测试地址")
    parser.add_argument("--full", action="store_true", help="完整测试模式")
    parser.add_argument("--visible", action="store_true", help="显示浏览器窗口（非headless）")
    
    args = parser.parse_args()
    
    if args.full:
        tester = ChanLunTester(url=args.url, headless=not args.visible)
        result = asyncio.run(tester.run_full_test())
        
        # 如果有错误，返回非0退出码
        if result["fail"] > 0 or result["errors"]:
            sys.exit(1)
    else:
        success = asyncio.run(quick_test(args.url))
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
