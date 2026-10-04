import asyncio
from playwright.async_api import async_playwright
import os
import re
from dotenv import load_dotenv, dotenv_values
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_env_path)
import logging
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def _clean_thinking_process(text):
    """移除大模型可能返回的思考过程（如 <think>...</think> 或 [thinking]... 等标记）"""
    if not text:
        return ""
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'\[thinking\].*?\[/thinking\]', '', text, flags=re.DOTALL)
    return text.strip()

def _extract_answer_text_from_response(response):
    """从 Chat Completions / Responses API 返回中提取最终文本答案。"""
    if isinstance(response, dict):
        # 兼容 OpenAI Chat Completions 格式
        choices = response.get("choices")
        if choices and len(choices) > 0:
            message = choices[0].get("message")
            if message:
                content = message.get("content")
                if content:
                    return str(content).strip()

        # 兼容旧的 Responses API 格式
        output_text = response.get("output_text")
        if output_text:
            return str(output_text).strip()

        text_parts = []
        for item in response.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                text = content.get("text")
                if text:
                    text_parts.append(text)
        return "\n".join(text_parts).strip()

    # 兼容对象属性形式的返回值
    choices = getattr(response, "choices", None)
    if choices and len(choices) > 0:
        message = choices[0]
        content = getattr(message, "content", None) or getattr(getattr(message, "message", None), "content", None)
        if content:
            return str(content).strip()

    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text.strip()

    text_parts = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                text_parts.append(text)

    return "\n".join(text_parts).strip()

async def set_video_speed(page):
    """将当前视频设置为 1.5 倍速，并尝试将清晰度调为流畅。"""
    try:
        await page.hover('div.videoArea')
        logger.info("已将鼠标悬停在视频区域")
        await asyncio.sleep(0.4)

        await page.click('div.speedBox')
        logger.info("已点击在速度设置区域")
        await asyncio.sleep(0.3)
        
        await page.click('div.speedTab15[rate="1.5"]')
        logger.info("已将播放速度设置为1.5倍")
        await asyncio.sleep(0.5)

        await page.hover('div.definiBox')
        logger.info("已悬停清晰度菜单")
        await asyncio.sleep(0.3)
        await page.click('b.line1bq.switchLine')
        logger.info("已将清晰度设置为流畅")
        await asyncio.sleep(0.3)
    except Exception as speed_error:
        logger.warning(f"调节播放速度时出现错误: {speed_error}")

async def check_and_handle_captcha(page):
    """检测验证码弹窗；出现时提示人工处理并等待消失。"""
    try:
        yidun_modal = await page.query_selector('div.yidun_modal')
        if yidun_modal and await yidun_modal.is_visible():
            logger.info("检测到验证码弹窗，等待用户处理...")
            print("【请接管】请手动完成弹窗验证码输入")
            
            try:
                await page.wait_for_selector('div.yidun_modal', state='hidden', timeout=600000)
                logger.info("验证码处理完成，继续播放")
                return True
            except Exception as wait_error:
                logger.warning(f"等待验证码结束时出错或超时: {wait_error}")
                return True
        return False
    except Exception as e:
        logger.warning(f"检测验证码弹窗时出现错误: {e}")
        return False

async def check_and_handle_integrity_commitment(page):
    """检测并处理“在线学习诚信承诺书”弹窗。"""
    try:
        dialog_selector = 'div[role="dialog"][aria-label="在线学习诚信承诺书"]'
        dialog = page.locator(dialog_selector).first
        if await dialog.count() == 0 or not await dialog.is_visible():
            return False

        logger.info("检测到在线学习诚信承诺书弹窗，准备自动确认")

        checkbox = dialog.locator('input[type="checkbox"]').first
        if await checkbox.count() > 0:
            if not await checkbox.is_checked():
                await checkbox.check(force=True)
                logger.info("已勾选诚信承诺复选框")
        else:
            logger.warning("未找到诚信承诺复选框，跳过自动处理")
            return False

        confirm_btn = dialog.locator('button.agree-btn, button:has-text("确认")').first
        if await confirm_btn.count() > 0:
            await confirm_btn.wait_for(state='visible', timeout=5000)

            for _ in range(10):
                if not await confirm_btn.is_disabled():
                    break
                await asyncio.sleep(0.2)

            await confirm_btn.click(timeout=5000)
            logger.info("已点击诚信承诺书“确认”按钮")

            try:
                await page.wait_for_selector(dialog_selector, state='hidden', timeout=5000)
                logger.info("诚信承诺书弹窗已关闭")
            except Exception:
                logger.info("诚信承诺书确认后弹窗未立即消失，继续执行")
            return True

        logger.warning("未找到诚信承诺书确认按钮，跳过自动处理")
        return False
    except Exception as e:
        logger.warning(f"处理诚信承诺书弹窗时出现错误: {e}")
        return False

async def is_video_finished(item):
    """通过 `b.fl.time_icofinish` 判断视频是否已完成。"""
    try:
        finished_indicator = await item.query_selector('b.fl.time_icofinish')
        return finished_indicator is not None and await finished_indicator.is_visible()
    except Exception as e:
        logger.warning(f"检测视频完成状态时出现错误: {e}")
        return False

async def ai_answer_question(page):
    """调用大模型回答视频题目，失败时回退到第一个选项。"""
    try:
        topic_title = await page.inner_text('p.topic-title')
        logger.info(f"已获取到题目")
        
        options = await page.query_selector_all('ul.topic-list li.topic-item')
        options_text = []
        for i, option in enumerate(options):
            option_text = await option.inner_text()
            options_text.append(f"{i+1}. {option_text}")
        
        options_text_str = "\n".join(options_text)
        prompt = f"""
        请根据以下题目和选项，选择正确答案。请只返回选项的数字索引，不要返回其他内容。
        对于单选题，返回一个数字（如1）。对于多选题，返回多个数字，用分号分隔（如1;3;4）。

        题目: {topic_title}
        
        选项:
        {options_text_str}
        """
        
        logger.info(f"发送给大模型的提示词: {prompt}")
        
        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("QWEN_API_KEY")
        )
        base_url = (
            os.getenv("DEEPSEEK_BASE_URL")
            or os.getenv("DASHSCOPE_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        model = os.getenv("ANSWER_MODEL", "deepseek-v4-flash-vision-exp")
        
        if not api_key:
            logger.warning("未配置 DEEPSEEK_API_KEY（兼容 DASHSCOPE_API_KEY / QWEN_API_KEY），使用默认方式答题（选择第一个选项）")
            await page.click('div#playTopic-dialog li.topic-item:first-child')
            return

        enable_reasoning = os.getenv("ENABLE_REASONING", "false").lower() == "true"
        logger.info(f"调用 Chat Completions API，模型: {model}，启用思考模式: {enable_reasoning}")

        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
        }
        if enable_reasoning:
            payload["extra_body"] = {"enable_thinking": True}

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            response = resp.json()

        answer_text = _extract_answer_text_from_response(response)
        logger.info(f"大模型返回的答案: {answer_text}")
        answer_text = _clean_thinking_process(answer_text)

        try:
            import re

            separated_numbers = re.findall(r'\b[1-9]\d*\b', answer_text)
            number_matches = []

            if separated_numbers:
                number_matches = separated_numbers
            else:
                continuous_digits = []
                for char in answer_text:
                    if char.isdigit() and char != '0':
                        continuous_digits.append(char)
                if continuous_digits:
                    number_matches = continuous_digits

            selected_indices = []

            if number_matches:
                selected_indices = [int(match) - 1 for match in number_matches if int(match) <= len(options)]

            # 如果没找到有效数字索引，尝试匹配字母 A, B, C, D...
            if not selected_indices:
                letters = re.findall(r'\b([A-Za-z])\b', answer_text)
                if letters:
                    for letter in letters:
                        idx = ord(letter.upper()) - ord('A')
                        if 0 <= idx < len(options):
                            selected_indices.append(idx)
                            logger.info(f"解析到字母选项: {letter.upper()}，对应索引 {idx + 1}")

            if selected_indices:
                for idx in selected_indices:
                    if 0 <= idx < len(options):
                        await options[idx].click()
                        logger.info(f"已选择第 {idx + 1} 个选项 (字母: {chr(ord('A') + idx)})")
                    else:
                        logger.warning(f"索引 {idx} 超出范围，跳过")
            else:
                logger.warning("没有有效的答案索引，选择第一个选项")
                await page.click('div#playTopic-dialog li.topic-item:first-child')
        except Exception as e:
            logger.warning(f"选择答案时出错: {e}，选择第一个选项")
            await page.click('div#playTopic-dialog li.topic-item:first-child')
                
    except Exception as e:
        logger.warning(f"大模型答题时出现错误: {e}，选择第一个选项")
        await page.click('div#playTopic-dialog li.topic-item:first-child')

async def zhihuishu_automation():
    """刷课主流程：登录、进入课程、播放未完成视频并处理答题弹窗。"""
    # 优先从 .env 直接读取配置，避免与系统环境变量（如 Windows 上的 USERNAME）冲突
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    config = dotenv_values(env_path) if os.path.exists(env_path) else {}
    env_course_name = config.get("COURSE_NAME") or os.getenv("COURSE_NAME")
    env_password = (
        config.get("ZHIHUISHU_PASSWORD")
        or config.get("PASSWORD")
        or os.getenv("ZHIHUISHU_PASSWORD")
        or os.getenv("PASSWORD")
    )
    
    env_username = (
        config.get("ZHIHUISHU_USERNAME")
        or config.get("USERNAME")
        or os.getenv("ZHIHUISHU_USERNAME")
        or os.getenv("ZH_USERNAME")
    )
    if not env_username:
        username_fallback = os.getenv("USERNAME")
        if username_fallback:
            # 检查是否为系统内置用户名，若是则忽略，防止在 Windows 上误用系统用户名作为智慧树账号
            system_user = None
            try:
                system_user = os.getlogin()
            except Exception:
                try:
                    import getpass
                    system_user = getpass.getuser()
                except Exception:
                    pass
            if username_fallback != system_user:
                env_username = username_fallback

    course_name = env_course_name or input("请输入要学习的课程名称: ")
    username = env_username or input("请输入用户名(手机号): ")
    userPassword = env_password or input("请输入密码: ")

    if env_course_name and env_username and env_password:
        print(f"使用环境变量配置: 课程={course_name}, 用户名={username}")
    
    env_llm_answer = config.get("ENABLE_LLM_ANSWER") or os.getenv("ENABLE_LLM_ANSWER")
    if env_llm_answer is not None:
        use_ai_answer = str(env_llm_answer).lower().strip() in ['true', '1', 'yes', 'y', '是']
        print(f"从环境变量读取 LLM 答题配置: {'启用' if use_ai_answer else '禁用'}")
    else:
        use_ai_answer = input("是否使用大模型自动答题？(y/n，默认为n): ").lower().strip() in ['y', 'yes', '是', '']
    
    if use_ai_answer:
        print("已启用大模型自动答题功能")
        api_key = (
            os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("QWEN_API_KEY")
        )
        if not api_key:
            print("警告: 未配置DEEPSEEK_API_KEY（兼容DASHSCOPE_API_KEY / QWEN_API_KEY），无法使用大模型答题功能")
            print("请在.env文件中配置DEEPSEEK_API_KEY，或选择不使用大模型答题")
            use_ai_answer = False
        else:
            answer_model = os.getenv("ANSWER_MODEL", "deepseek-v4-flash-vision-exp")
            print(f"已检测到API密钥，答题模型: {answer_model}，大模型答题功能可用")
    else:
        print("未启用大模型自动答题功能，将默认选择第一个选项")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=False, 
                channel='chrome',
                args=['--mute-audio']
            )
        except Exception as launch_err:
            logger.warning(f"启动 Chrome 浏览器通道失败 (可能是未安装 Chrome): {launch_err}。尝试使用默认 Chromium 启动...")
            browser = await p.chromium.launch(
                headless=False,
                args=['--mute-audio']
            )
        page = await browser.new_page()
        
        try:
            print("正在打开智慧树官网...")
            await page.goto('https://www.zhihuishu.com')
            logger.info("已打开智慧树官网")
        
            print("正在打开登陆页面...")
            await page.click('text="登录"')
            logger.info("已点击登录按钮")
            
            logger.info("正在等待登录页面出现...")
            user_input_selector = 'input[name="mobile"], input[placeholder*="手机号"], input[name="username"]'
            await page.wait_for_selector(user_input_selector, timeout=10000)
            logger.info("登录页面已出现")

            # 确保处于“账号登录”标签页
            try:
                account_tab = page.locator('.el-tabs__item:has-text("账号登录")').first
                if await account_tab.count() > 0:
                    tab_class = await account_tab.get_attribute("class") or ""
                    if "is-active" not in tab_class:
                        await account_tab.click()
                        await asyncio.sleep(0.5)
            except Exception as tab_err:
                logger.debug(f"切换账号登录标签提示: {tab_err}")

            print("正在输入手机号、密码")
            logger.info("正在输入手机号...")
            await page.locator(user_input_selector).first.fill(username)
            logger.info("手机号已输入")

            logger.info("正在输入密码...")
            pwd_input_selector = 'input[type="password"], input[placeholder*="密码"], input[name="password"]'
            await page.locator(pwd_input_selector).first.fill(userPassword)
            logger.info("密码已输入")

            # 勾选用户协议与隐私政策（新版智慧树必须勾选才能提交）
            try:
                privacy_checkbox = page.locator('.privacy-checkbox input[type="checkbox"], input[type="checkbox"].el-checkbox__original').first
                if await privacy_checkbox.count() > 0 and not await privacy_checkbox.is_checked():
                    logger.info("正在勾选用户协议与隐私政策...")
                    await page.locator('.privacy-checkbox, .privacy label, .el-checkbox').first.click()
                    logger.info("已勾选用户协议")
            except Exception as agree_err:
                logger.debug(f"勾选协议处理异常: {agree_err}")

            await asyncio.sleep(0.8)

            print("正在点击登录按钮...")
            login_btn = page.locator('.btn-block__grandient_login, .wall-sub-btn, .login-bottom:has-text("登录"), button:has-text("登录")').first
            await login_btn.click()
            logger.info("已点击登录按钮")
            logger.info("正在等待页面跳转到学习页面...")
            print("【请接管】请手动完成验证码输入（跳转到课程列表页面会自动进行下一步）")

            await page.wait_for_url(re.compile(r'.*zhihuishu\.com/.*onlinestuh5.*'), timeout=60000)
            print("已跳转到课程列表页面")
            
            await asyncio.sleep(5)
            
            logger.info(f"正在查找'{course_name}'课程...")
            await page.wait_for_selector('div.courseName', timeout=10000)
            logger.info(f"找到课程列表，正在点击'{course_name}'...")
            await page.click(f'div.courseName:has-text("{course_name}")')
            logger.info(f"'{course_name}'课程已点击")
            
            logger.info("正在等待页面跳转和加载...")
            try:
                # 动态等待：代替固定的 sleep(6)，等待特征元素（课程列表或已知弹窗）挂载到 DOM
                await page.wait_for_selector('ul.list, [aria-label="在线学习诚信承诺书"], [aria-label="课程提醒"]', state='attached', timeout=30000)
                # 可选：等待后续的网络请求回落，避免界面卡顿
                await page.wait_for_load_state('networkidle', timeout=5000)
            except Exception as wait_err:
                logger.warning(f"智能等待可能没有完全捕捉到预设元素，继续执行: {wait_err}")

            await check_and_handle_integrity_commitment(page)

            print("已跳转到课程学习页面，正在关闭弹窗...")

            # 检测“学习时间已经结束”温馨提示弹窗
            logger.info("正在检测是否有“学习时间已经结束”温馨提示弹窗...")
            try:
                warm_tip_dialog = page.locator('div.el-dialog[aria-label="温馨提示"]:has-text("学习时间已经结束")').first
                if await warm_tip_dialog.count() > 0 and await warm_tip_dialog.is_visible():
                    logger.info("检测到“学习时间已经结束”温馨提示弹窗！")
                    print("【温馨提示】学习时间已经结束, 观看视频将不再计进度")
                    
                    # 尝试点击“我知道了”按钮
                    know_btn = warm_tip_dialog.locator('button:has-text("我知道了")').first
                    if await know_btn.count() > 0 and await know_btn.is_visible():
                        await know_btn.click(timeout=3000)
                        logger.info("已点击“我知道了”按钮关闭弹窗")
                    else:
                        # 如果没找到“我知道了”按钮，尝试点击右上角关闭按钮
                        close_btn = warm_tip_dialog.locator('button[aria-label="Close"]').first
                        if await close_btn.count() > 0 and await close_btn.is_visible():
                            await close_btn.click(timeout=3000)
                            logger.info("已点击右上角关闭按钮")
                    await asyncio.sleep(1)
                else:
                    logger.info("未检测到“学习时间已经结束”温馨提示弹窗，继续执行")
            except Exception as warm_tip_error:
                logger.info(f"处理“学习时间已经结束”温馨提示弹窗异常，继续执行: {warm_tip_error}")

            # 处理关闭按钮0（公众号课程提醒弹窗)
            
            logger.info("正在查找关闭按钮0(公众号课程提醒弹窗)...")
            try:
                remind_dialog = page.locator('div[role="dialog"][aria-label="课程提醒"]').first
                try:
                    await remind_dialog.wait_for(state='visible', timeout=3000)
                    logger.info("找到关闭按钮0(公众号课程提醒弹窗)，准备关闭...")
                    
                    bound_btn = remind_dialog.locator('div.rlready-bound-btn').first
                    later_btn = remind_dialog.locator('div.talk-later-btn').first
                    
                    if await bound_btn.count() > 0 and await bound_btn.is_visible():
                        await bound_btn.click(timeout=3000)
                        logger.info("已点击“已绑定，不再提示”按钮 (关闭按钮0)")
                    elif await later_btn.count() > 0 and await later_btn.is_visible():
                        await later_btn.click(timeout=3000)
                        logger.info("已点击“下次再说”按钮 (关闭按钮0)")
                        
                    await asyncio.sleep(1)
                except Exception:
                    logger.info("未检测到课程提醒弹窗，继续执行")
            except Exception as close_btn0_error:
                logger.info(f"课程提醒弹窗(关闭按钮0)处理异常，继续执行: {close_btn0_error}")

            # 处理关闭按钮1（学前必读弹窗）
            logger.info("正在等待关闭按钮1...")
            try:
                await page.wait_for_selector('i.iconfont.iconguanbi', timeout=10000)
                logger.info("找到关闭按钮1，正在点击...")
                await page.click('i.iconfont.iconguanbi')
                logger.info("已点击关闭按钮1")
                await asyncio.sleep(1)
            except Exception as close_btn1_error:
                logger.info(f"关闭按钮1不可用，继续执行: {close_btn1_error}")
            
            # 处理关闭按钮2（AI助手信息弹窗）
            logger.info("正在查找关闭按钮2...")
            try:
                await page.wait_for_selector('img.icon', timeout=5000)
                logger.info("找到关闭按钮2，正在点击...")
                await page.click('img.icon')
                logger.info("已点击关闭按钮2")
                await asyncio.sleep(1)
            except Exception as close_btn2_error:
                logger.info(f"关闭按钮2不可用，继续执行: {close_btn2_error}")

            # 处理关闭按钮3（AI助手悬浮球）
            logger.info("正在查找关闭按钮3（AI助手悬浮球）...")
            try:
                await page.wait_for_selector('img.ai-close-icon', timeout=5000)
                logger.info("找到关闭按钮3，正在点击...")
                await page.click('img.ai-close-icon')
                logger.info("已点击关闭按钮3")
                await asyncio.sleep(1)
            except Exception as close_btn3_error:
                logger.info(f"关闭按钮3不可用，继续执行: {close_btn3_error}")

            # 处理关闭按钮4（浏览器建议弹窗）
            logger.info("正在查找关闭按钮4（浏览器建议弹窗）...")
            try:
                no_hint_btn = page.locator('a:has-text("不再提示")').first
                if await no_hint_btn.count() > 0 and await no_hint_btn.is_visible():
                    logger.info("找到关闭按钮4，正在点击...")
                    await no_hint_btn.click(timeout=5000)
                    logger.info("已点击关闭按钮4")
                    await asyncio.sleep(1)
                else:
                    logger.info("未检测到浏览器建议弹窗（不再提示），继续执行")
            except Exception as close_btn4_error:
                logger.info(f"关闭按钮4处理异常，继续执行: {close_btn4_error}")
            
            print("已关闭弹窗，正在查找未完成的课程...")
            found_unfinished_video = False
            try:
                await page.wait_for_selector('ul.list', timeout=10000)
                
                catalog_items = await page.query_selector_all('ul.list > li, ul.list > div > li, ul.list > div > ul > li')
                
                for item in catalog_items:
                    item_class = await item.get_attribute('class')
                    if item_class and 'video' in item_class:
                        is_finished = await is_video_finished(item)
                        
                        if not is_finished:
                            title_span = await item.query_selector('span.catalogue_title')
                            if title_span:
                                logger.info("找到未完成的课程，正在点击...")
                                await title_span.click()
                                logger.info("已点击未完成课程的标题")
                                found_unfinished_video = True
                                
                                await asyncio.sleep(3)
                                
                                await check_and_handle_captcha(page)
                                
                                try:
                                    dialog = await page.query_selector('div#playTopic-dialog')
                                    if dialog and await dialog.is_visible():
                                        logger.info("检测到div#playTopic-dialog答题弹框")
                                        await asyncio.sleep(2)
                                        
                                        if use_ai_answer:
                                            await ai_answer_question(page)
                                            await asyncio.sleep(1)
                                        else:
                                            await page.click('div#playTopic-dialog li.topic-item:first-child')
                                            logger.info("已点击第一个选项")
                                            await asyncio.sleep(1)
                                        
                                        await page.click('div:text("关闭")')
                                        logger.info("已点击关闭答题")
                                except Exception as e:
                                    logger.warning(f"处理答题弹框时出现错误: {e}")
                                
                                await asyncio.sleep(3)
                                logger.info("正在查找视频区域...")
                                await page.wait_for_selector('div.videoArea', timeout=10000)
                                logger.info("找到视频区域，正在点击播放")
                                await page.click('div.videoArea')
                                logger.info("已点击视频区域开始播放")
                                
                                await asyncio.sleep(1)
                                
                                logger.info("正在调节视频播放速度...")
                                
                                await set_video_speed(page)
                                
                                break
                            else:
                                logger.info("未找到课程标题，继续查找下一个...")
                                continue
                        else:
                            logger.info("视频已完成，跳过...")
                else:
                    if not found_unfinished_video:
                        logger.info("未找到未完成的课程")
                        print("【执行结束】没有更多未完成的视频")
            
            except Exception as e:
                logger.error(f"查找未完成课程时出现错误: {e}")
            
            if found_unfinished_video:
                print("正在等待答题弹框出现...")
                
                import time
                last_completion_check_time = 0
                
                while True:
                    try:
                        current_time = time.time()
                        current_video_completed = False
                        
                        # 降低视频完成状态的检测频率，避免频繁 DOM 查询导致的高 CPU 占用（每 5 秒检测一次）
                        if current_time - last_completion_check_time > 5:
                            last_completion_check_time = current_time
                            
                            # 直接定位当前播放的视频节点
                            current_item = await page.query_selector('ul.list li.video.current_play, ul.list div li.video.current_play, ul.list div ul li.video.current_play')
                            if current_item and await is_video_finished(current_item):
                                current_video_completed = True
                                logger.info("当前视频已完成")
                        
                        if current_video_completed:
                            next_unfinished_video_found = False
                            # 只有当前视频完成时，才拉取完整的列表去寻找下一个未完成视频
                            catalog_items = await page.query_selector_all('ul.list > li, ul.list > div > li, ul.list > div > ul > li')
                            for item in catalog_items:
                                item_class = await item.get_attribute('class')
                                if item_class and 'video' in item_class:
                                    is_finished = await is_video_finished(item)
                                    
                                    if not is_finished:
                                        title_span = await item.query_selector('span.catalogue_title')
                                        if title_span:
                                            logger.info("找到下一个未完成的课程，正在切换...")
                                            await title_span.click()
                                            logger.info("已切换到下一个未完成课程")
                                            await asyncio.sleep(3)
                                            
                                            await check_and_handle_captcha(page)
                                            
                                            try:
                                                dialog = await page.query_selector('div#playTopic-dialog')
                                                if dialog and await dialog.is_visible():
                                                    logger.info("检测到div#playTopic-dialog弹框")
                                                    await asyncio.sleep(2)
                                                    
                                                    if use_ai_answer:
                                                        await ai_answer_question(page)
                                                        await asyncio.sleep(1)
                                                    else:
                                                        await page.click('div#playTopic-dialog li.topic-item:first-child')
                                                        logger.info("已点击第一个选项")
                                                        await asyncio.sleep(1)
                                                    
                                                    await page.click('div:text("关闭")')
                                                    logger.info("已点击关闭答题")
                                                    
                                                    logger.info("答题后点击视频区域以继续播放")
                                                    await page.click('div.videoArea')
                                                    logger.info("已点击视频区域，继续播放")
                                            except Exception as e:
                                                logger.warning(f"处理答题弹框时出现错误: {e}")
                                            
                                            logger.info("切换视频后点击视频区域以开始播放")
                                            await page.click('div.videoArea')
                                            logger.info("已点击视频区域开始播放")
                                            
                                            await set_video_speed(page)
                                            
                                            next_unfinished_video_found = True
                                            last_completion_check_time = time.time()
                                            break
                                        else:
                                            logger.info("未找到课程标题，继续查找下一个...")
                                            continue
                                    else:
                                        logger.info("视频已完成，跳过...")
                            
                            if not next_unfinished_video_found:
                                print("【执行结束】没有更多未完成的视频")
                                break
                        
                        await check_and_handle_captcha(page)
                        
                        # 快速检测答题弹窗
                        try:
                            await page.wait_for_selector('div#playTopic-dialog', state='visible', timeout=1000)
                            logger.info("检测到div#playTopic-dialog弹框")
                            
                            if use_ai_answer:
                                await ai_answer_question(page)
                                await asyncio.sleep(1)
                            else:
                                await page.click('div#playTopic-dialog li.topic-item:first-child')
                                logger.info("已点击第一个选项")
                                await asyncio.sleep(1)
                            
                            await page.click('div:text("关闭")')
                            logger.info("已点击关闭答题")
                            
                            logger.info("答题后点击视频区域以继续播放")
                            await page.click('div.videoArea')
                            logger.info("已点击视频区域，继续播放...")
                        except Exception as wait_err:
                            pass
                        
                        await asyncio.sleep(1.0)
                        
                    except Exception as loop_error:
                        logger.debug(f"轮询答题弹窗时出现可恢复异常: {loop_error}")
                        await asyncio.sleep(1.0)
                        continue
            
            print("【执行结束】脚本执行完成，浏览器保持打开状态...")
            
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"执行过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
            print("【发生错误】脚本已停止运行。浏览器保持打开状态以供排查原因。您可以手动接管，或按 Ctrl+C 退出程序。")
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass
        finally:
            logger.info("Playwright 浏览器上下文已关闭")

if __name__ == "__main__":
    asyncio.run(zhihuishu_automation())
