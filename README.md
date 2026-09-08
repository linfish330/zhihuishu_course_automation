# 智慧树视频课程自动学习脚本

![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-1.40-2EAD33?style=flat-square&logo=playwright&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-F5A623?style=flat-square)

基于 Playwright 与 DeepSeek 大模型的智慧树平台全自动视频学习工具。自动登录、1.5 倍速播放、AI 答题、自动连播。

---

## 功能特性

- 自动登录并关闭诚信承诺书、公众号提醒、学前必读、AI 助手等弹窗
- 自动将视频播放速度调整为 1.5 倍并调至流畅清晰度
- 视频播放中途弹出随堂测试时，自动调用 DeepSeek AI 答题（可通过 `ENABLE_LLM_ANSWER` 开关控制）
- 当前视频完成后自动切换并播放下一个未完成视频
- 采用智能轮询检测（5 秒间隔），大幅降低 CPU 占用，避免电脑发烫
- 遇到滑块验证码时暂停程序，等待用户手动完成后自动继续
- 若系统未安装标准 Google Chrome，自动降级使用 Playwright 自带的 Chromium

---

## 快速开始

> 需要 Python 3.10+ 环境。如未安装，请先前往 [Python 官网](https://www.python.org/downloads/) 下载安装。

```bash
# 1. 克隆项目
git clone https://github.com/linfish330/zhihuishu_course_automation.git
cd zhihuishu_course_automation

# 2. 安装依赖
pip install -r requirements.txt
playwright install

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入账号密码和 API Key

# 4. 运行
python zhihuishu_course_automation.py
```

---

## 配置说明

复制 `.env.example` 为 `.env`，按需修改以下参数：

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `ZHIHUISHU_USERNAME` | 是 | 智慧树登录手机号 |
| `ZHIHUISHU_PASSWORD` | 是 | 智慧树登录密码 |
| `COURSE_NAME` | 是 | 要学习的课程完整名称 |
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥（兼容 `DASHSCOPE_API_KEY` / `QWEN_API_KEY`） |
| `DEEPSEEK_BASE_URL` | 否 | API 端点，默认 `https://api.deepseek.com/v1`（兼容 `DASHSCOPE_BASE_URL`） |
| `ENABLE_LLM_ANSWER` | 否 | 是否使用大模型自动答题，默认 `true` |
| `ANSWER_MODEL` | 否 | 答题模型名称，默认 `deepseek-v4-flash-vision-exp` |
| `ENABLE_REASONING` | 否 | 是否启用推理模式，默认 `false` |

> API 密钥可前往 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 申请。

### 切换其他 AI 服务

本工具所有请求走标准 OpenAI Chat Completions 接口，**不限于 DeepSeek**。只需修改 API 地址、API 密钥和 `ANSWER_MODEL` 变量即可切换到任何兼容 OpenAI 接口的服务商。

**阿里云百炼（通义千问）：**

```env
DEEPSEEK_API_KEY="sk-your-dashscope-key"
DEEPSEEK_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
ANSWER_MODEL="qwen3.6-plus"
```

**硅基流动 (SiliconFlow)：**

```env
DEEPSEEK_API_KEY="sk-your-siliconflow-key"
DEEPSEEK_BASE_URL="https://api.siliconflow.cn/v1"
ANSWER_MODEL="Qwen/Qwen2.5-7B-Instruct"
```

**OpenAI：**

```env
DEEPSEEK_API_KEY="sk-your-openai-key"
DEEPSEEK_BASE_URL="https://api.openai.com/v1"
ANSWER_MODEL="gpt-4o-mini"
```

> 任何提供 OpenAI 兼容接口的服务均可接入，只需确保 Base URL 以 `/v1` 结尾、模型名称与服务商一致即可。

---

## 运行流程

1. 程序启动浏览器，自动填写账号密码登录智慧树
2. 登录时若出现滑块验证，控制台提示手动完成，完成后程序自动继续
3. 自动定位目标课程，进入视频播放页面
4. 静音播放视频，调整为 1.5 倍速
5. 遇到随堂测试时调用 AI 答题
6. 当前视频结束后自动切换到下一个未完成视频，循环直至全部完成

---

## 技术栈

| 类别 | 技术 | 版本 |
| --- | --- | --- |
| 语言 | Python | 3.10+ |
| 浏览器自动化 | Playwright | 1.40.0 |
| LLM API | DeepSeek（OpenAI 兼容接口） | OpenAI 兼容接口 |
| HTTP 客户端 | httpx | 0.25.2 |
| 配置管理 | python-dotenv | 1.0.0 |

---

## 常见问题

**Q: 运行提示 `'python' 不是内部或外部命令`**
安装 Python 时务必勾选 `Add Python to PATH`，或卸载重装。

**Q: 提示 `ModuleNotFoundError: No module named 'playwright'`**
在项目目录下重新运行 `pip install -r requirements.txt`。如不行，尝试 `pip3`。

**Q: 启动时报错 `Executable ... not found`**
运行 `playwright install` 下载浏览器内核。

**Q: API 调用失败**
检查 `.env` 中的 API Key 是否正确；登录对应服务商控制台检查余额与调用权限。

**Q: 智慧树页面改版导致脚本失效**
到 [GitHub Issues](https://github.com/linfish330/zhihuishu_course_automation/issues) 反馈。

**Q: 如何使用其他模型**
修改 `.env` 中的 `DEEPSEEK_BASE_URL`（或 `DASHSCOPE_BASE_URL`）、API 密钥以及 `ANSWER_MODEL` 为对应服务的地址、密钥和模型名称即可。

---

## 免责声明

本项目仅供学习与技术交流使用，请勿用于商业用途。使用自动化工具可能会违反平台协议，所带来的后果由使用者自行承担。AI 模型的回答可能存在不准确性，成绩风险由使用者自负。
