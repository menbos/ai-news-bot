<div align="center">

# AI 新闻机器人

🤖 **您的 AI 新闻助手** — 每日自动获取个性化 AI 新闻摘要，保持信息灵通

[![GitHub Stars](https://img.shields.io/github/stars/giftedunicorn/ai-news-bot?style=flat-square&logo=github&color=yellow)](https://github.com/giftedunicorn/ai-news-bot/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/giftedunicorn/ai-news-bot?style=flat-square&logo=github&color=blue)](https://github.com/giftedunicorn/ai-news-bot/network/members)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg?style=flat-square)](LICENSE)

[![Discord](https://img.shields.io/badge/Discord-加入社区-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/AtfQPh8T2T)
[![邮件](https://img.shields.io/badge/邮件-Gmail_SMTP-00D4AA?style=flat-square)](https://gmail.com/)
[![Webhook](https://img.shields.io/badge/Webhook-支持-00D4AA?style=flat-square)](#)
[![Slack](https://img.shields.io/badge/Slack-集成-00D4AA?style=flat-square)](https://slack.com/)
[![Telegram](https://img.shields.io/badge/Telegram-机器人-00D4AA?style=flat-square)](https://telegram.org/)

[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-自动化-2088FF?style=flat-square&logo=github-actions&logoColor=white)](https://github.com/giftedunicorn/ai-news-bot)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.5-FF6B6B?style=flat-square&logo=anthropic&logoColor=white)](https://www.anthropic.com)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-支持-4285F4?style=flat-square&logo=ai&logoColor=white)](https://www.deepseek.com)

</div>

---

## 📑 快速导航

<div align="center">

| [✨ 功能特点](#功能特点) | [🚀 快速开始](#快速开始本地开发) |      [⚙️ 配置](#配置)       | [🤖 LLM 提供商](#llm-提供商配置) |
| :----------------------: | :------------------------------: | :-------------------------: | :------------------------------: |
| [🌍 语言配置](#语言配置) |   [📧 邮件设置](#邮件设置指南)   | [🔗 Webhook](#webhook-集成) |     [🔧 故障排除](#故障排除)     |

</div>

---

## 功能特点

- **多 LLM 提供商支持**：可选择 Claude、DeepSeek、Gemini、Grok 或 OpenAI 进行新闻生成
- **实时新闻获取**：从 RSS 源获取真实新闻，确保内容准确、及时
- **AI 驱动的新闻生成**：使用您偏好的 LLM 提供商生成全面的 AI 新闻摘要
- **网络搜索集成**：可选的 DuckDuckGo 网络搜索，获取更多新闻来源
- **精美的邮件格式**：自动将 AI 内容转换为精美的 HTML 邮件 - 无 markdown，只有简洁专业的设计
- **可定制的提示词**：9 个预设模板（综合、研究、商业、技术等）或创建自定义模板
- **多语言支持**：支持 13+ 种语言生成新闻，包括中文、英文、西班牙语、法语、日语等
- **中文新闻源支持**：内置中文 AI 新闻源支持（36 氪、机器之心等）
- **多通知渠道**：支持邮件（Gmail SMTP）、Webhook、Slack、Telegram 和 Discord 通知
- **灵活配置**：通过 YAML 配置文件轻松自定义主题和通知设置
- **自动调度**：GitHub Actions 工作流支持每日自动执行
- **健壮的错误处理**：全面的日志记录和重试逻辑
- **邮件客户端兼容**：完美支持 Gmail、Outlook、Apple Mail 和移动邮件应用
- **简单邮件设置**：只需使用您的 Gmail 账户和应用专用密码，无需第三方邮件服务

### 📸 示例截图

<div align="center">

| 中文邮件 | 英文邮件 |
|:-------------:|:-------------:|
| ![中文 AI 新闻摘要](image/screenshot1.png) | ![英文 AI 新闻摘要](image/screenshot2.png) |
| 中文版新闻摘要示例 | 英文版新闻摘要示例 |

</div>

## 🚀 部署选项

选择您的部署方式：

| 方式               | 配置方法     | 使用场景               |
| ------------------ | ------------ | ---------------------- |
| **GitHub Actions** | 仓库 Secrets | 自动化每日运行（推荐） |
| **本地开发**       | `.env` 文件  | 本地测试或手动运行     |

> 💡 **推荐**：使用 GitHub Actions 实现自动化每日新闻推送。使用本地开发进行测试或自定义。

## 快速开始（GitHub Actions - 推荐）

GitHub Actions 提供自动化的每日新闻推送，无需任何服务器设置。配置一次，自动接收新闻摘要。

### 步骤 1：Fork 或克隆仓库

将此仓库 Fork 到您的 GitHub 账户，或克隆它：

```bash
git clone <your-repo-url>
cd ai-news-bot
```

### 步骤 2：添加 GitHub 仓库 Secrets

导航到您的 GitHub 仓库：

```
仓库 → Settings → Secrets and variables → Actions → Repository secrets → New repository secret
```

添加以下 secrets：

#### ✅ 必需的 Secrets

| Secret 名称            | 示例值                                             | 描述                                       |
| ---------------------- | -------------------------------------------------- | ------------------------------------------ |
| `LLM_PROVIDER`         | `claude`、`deepseek`、`gemini`、`grok` 或 `openai` | LLM 提供商（默认：`claude`）               |
| `ANTHROPIC_API_KEY`    | `sk-ant-api03-xxx...`                              | 您的 Anthropic API 密钥（使用 Claude 时）  |
| `DEEPSEEK_API_KEY`     | `sk-xxx...`                                        | 您的 DeepSeek API 密钥（使用 DeepSeek 时） |
| `GOOGLE_API_KEY`       | `AIza...`                                          | 您的 Google API 密钥（使用 Gemini 时）     |
| `XAI_API_KEY`          | `xai-...`                                          | 您的 xAI API 密钥（使用 Grok 时）          |
| `OPENAI_API_KEY`       | `sk-...`                                           | 您的 OpenAI API 密钥（使用 OpenAI 时）     |
| `NOTIFICATION_METHODS` | `email`                                            | 通知渠道（逗号分隔）                       |

#### 📧 邮件 Secrets（如果使用邮件通知）

| Secret 名称          | 示例值                  | 描述                                                                        |
| -------------------- | ----------------------- | --------------------------------------------------------------------------- |
| `GMAIL_ADDRESS`      | `you@gmail.com`         | 您的 Gmail 邮箱地址                                                         |
| `GMAIL_APP_PASSWORD` | `xxxx xxxx xxxx xxxx`   | Gmail 应用专用密码（[点击获取](https://myaccount.google.com/apppasswords)） |
| `EMAIL_TO`           | `recipient@example.com` | 收件人邮箱地址                                                              |

详细的 Gmail 配置说明请参见[邮件设置指南](#邮件设置指南)。

#### 🌍 可选的 Secrets

| Secret 名称            | 示例值                     | 描述                                                       |
| ---------------------- | -------------------------- | ---------------------------------------------------------- |
| `AI_RESPONSE_LANGUAGE` | `zh` 或 `es` 或 `en,zh,ja` | 语言代码（默认 `en`）。多语言用逗号分隔                    |

其他通知渠道（Webhook、Slack、Telegram、Discord）配置请参见[完整配置表](#github-actions-设置)。

### 步骤 3：启用 GitHub Actions

确保 GitHub Actions 已启用：

```
仓库 → Settings → Actions → General → Allow all actions and reusable workflows
```

### 步骤 4：测试您的设置

手动触发工作流以验证一切正常：

```
仓库 → Actions 标签 → Daily AI News Digest → Run workflow 按钮
```

### 步骤 5：自动化每日推送

工作流将在每天 UTC 时间午夜（北京时间上午 8:00）自动运行。要自定义调度时间，编辑 `.github/workflows/daily-news.yml`：

```yaml
schedule:
  - cron: "0 0 * * *" # UTC 午夜（当前设置）
  - cron: "0 9 * * *" # UTC 上午 9:00
  - cron: "0 */12 * * *" # 每 12 小时
```

🎉 **完成！** 您现在将自动接收每日 AI 新闻摘要。

---

## 本地开发（可选）

用于测试或在您的计算机上手动运行：

### 1. 克隆仓库

```bash
git clone <your-repo-url>
cd ai-news-bot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制示例文件并填入您的凭证：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入实际值：

```env
# LLM 提供商配置
LLM_PROVIDER=claude  # 可选：'claude' 或 'deepseek'

# API 密钥（根据使用的提供商填写）
ANTHROPIC_API_KEY=your_api_key_here      # Claude 使用
DEEPSEEK_API_KEY=your_deepseek_api_key   # DeepSeek 使用

# Gmail 配置（设置简单！）
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # 16位应用专用密码（不是Gmail普通密码）
EMAIL_TO=recipient@example.com

# 可选：Webhook 配置
WEBHOOK_URL=https://your-webhook-url.com/endpoint

# 通知方式（逗号分隔）
NOTIFICATION_METHODS=email,webhook

# 语言设置（可选，默认为 'en'）
# 单一语言：
AI_RESPONSE_LANGUAGE=zh
# 多语言（逗号分隔）：
# AI_RESPONSE_LANGUAGE=en,zh,ja
```

> **注意**：`.env` 文件仅用于**本地开发**。对于 GitHub Actions 自动化，您需要将这些配置为 **GitHub Secrets**（参见下方 [GitHub Actions 设置](#github-actions-设置)）。

### 4. 自定义新闻提示词（可选）

机器人使用**优化的简洁提示词**（15 行 vs 典型系统的 50+ 行）生成高质量的新闻摘要。

**默认提示词**（在 config.yaml 中）：

```yaml
Summarize 10 recent AI news items (5 international + 5 domestic) covering: {topics}

Format:
International News:
1. [Headline]
[2-3 sentence summary]
Source: [Name]

Domestic News:
1. [Headline]
...

Rules: Recent news, no markdown, clear language
```

**为何简洁：**

- ✅ 处理更快
- ✅ 成本更低
- ✅ 更易维护
- ✅ 无冗余

**多语言支持：**

提示词使用英文（最适合 Claude），但输出可以是 **13+ 种语言**：

```bash
# 在 .env 文件中
AI_RESPONSE_LANGUAGE=zh  # 中文输出
AI_RESPONSE_LANGUAGE=es  # 西班牙语输出
AI_RESPONSE_LANGUAGE=ja  # 日语输出
# 支持：en, zh, es, fr, ja, de, ko, pt, ru, ar, hi, it, nl
```

**预设模板**（config.examples.yaml）：

1. 综合（默认）- 均衡覆盖
2. 研究 - 学术焦点
3. 商业 - 行业与融资
4. 技术 - 工程深度
5. 创业 - 早期公司
6. 政策 - 法规
7. 周报 - 热门故事
8. 简洁 - 超简短
9. 中文 - 中文示例

📖 **完整指南**：参见 `config.examples.yaml` 了解自定义和多语言详情。

### 5. 本地运行

```bash
python main.py
```

---

## 配置

### 配置变量

机器人需要以下配置。设置方式取决于您的部署环境：

- **本地开发**：使用 `.env` 文件（参见[快速开始](#快速开始本地开发)）
- **GitHub Actions**：使用 GitHub 仓库 Secrets（参见 [GitHub Actions 设置](#github-actions-设置)）

| 变量                   | 是否必需             | 描述                                                                                                          |
| ---------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------- |
| `LLM_PROVIDER`         | 可选                 | LLM 提供商：`claude`、`deepseek`、`gemini`、`grok` 或 `openai`（默认：`claude`）                              |
| `ANTHROPIC_API_KEY`    | 使用 Claude 时需要   | 您的 Anthropic API 密钥（[获取](https://console.anthropic.com/)）                                             |
| `DEEPSEEK_API_KEY`     | 使用 DeepSeek 时需要 | 您的 DeepSeek API 密钥（[获取](https://platform.deepseek.com/)）                                              |
| `GOOGLE_API_KEY`       | 使用 Gemini 时需要   | 您的 Google API 密钥（[获取](https://makersuite.google.com/app/apikey)）                                      |
| `XAI_API_KEY`          | 使用 Grok 时需要     | 您的 xAI API 密钥（[获取](https://x.ai/)）                                                                                                |
| `OPENAI_API_KEY`       | 使用 OpenAI 时需要   | 您的 OpenAI API 密钥（[获取](https://platform.openai.com/api-keys)）                                                                      |
| `NOTIFICATION_METHODS` | ✅ 必需              | 逗号分隔的列表：`email`、`webhook` 或 `email,webhook`                                                                                     |
| `AI_RESPONSE_LANGUAGE` | 可选                 | AI 响应的语言代码（默认：`en`）。多语言用逗号分隔（如 `en,zh,ja`）。支持：`zh`、`es`、`fr`、`ja`、`de`、`ko`、`pt`、`ru`、`ar`、`hi`、`it`、`nl` |
| `GMAIL_ADDRESS`        | 使用 Gmail 时需要    | 您的 Gmail 邮箱地址                                                                                           |
| `GMAIL_APP_PASSWORD`   | 使用 Gmail 时需要    | Gmail 应用专用密码（16 位，不是普通密码）                                                                     |
| `EMAIL_TO`             | 使用邮件时需要       | 收件人邮箱地址                                                                                                |
| `WEBHOOK_URL`          | 使用 webhook 时需要  | Webhook 端点 URL                                                                                              |

### 配置文件（config.yaml）

`config.yaml` 文件允许您自定义新闻摘要行为：

**LLM 配置**：

- **Provider（提供商）**：选择 `claude`、`deepseek`、`gemini`、`grok` 或 `openai`
- **Model（模型）**：可选指定特定模型版本

**新闻配置**：

- **use_real_sources**：启用从 RSS 源获取新闻（推荐，默认：true）
- **max_items_per_source**：每个源的最大新闻条目数（默认：10）
- **Topics（主题）**：新闻选择的焦点领域（可选，引导 AI）
- **Prompt Template（提示词模板）**：LLM 的指令模板
  - 默认：综合 15-20 条新闻摘要，带分类标题
  - 可完全自定义提示词
  - 参见 `config.examples.yaml` 中的 9 个预设模板

**日志设置**：控制日志详细程度和格式

**示例结构**：

```yaml
llm:
  provider: claude # 选项：'claude'、'deepseek'、'gemini'、'grok'、'openai'
  # model: claude-sonnet-4-5-20250929  # 可选

news:
  max_items_per_source: 10

  topics:
    - "大语言模型 (LLM)"
    - "AI 智能体和自主系统"
    - "产品发布"

  prompt_template: |
    您的自定义提示词...
    焦点：{topics}

logging:
  level: INFO
  format: "%(asctime)s - %(levelname)s - %(message)s"
```

### LLM 提供商配置

机器人支持 **5 个 LLM 提供商**。在 `config.yaml` 或环境变量中配置：

#### Claude (Anthropic) - 默认

```yaml
llm:
  provider: claude
  model: claude-sonnet-4-5-20250929 # 可选，未设置则使用默认值
```

**可用模型：**

- `claude-sonnet-4-5-20250929` - 最新 Sonnet（默认）- 最适合大多数任务
- `claude-3-5-sonnet-20241022` - 上一版本 Sonnet

**定价：** $3 输入 / $15 输出 每百万 token

#### DeepSeek - 高性价比替代方案

```yaml
llm:
  provider: deepseek
  model: deepseek-chat # 可选，未设置则使用默认值
```

**可用模型：**

- `deepseek-chat` - 通用聊天模型（默认）
- `deepseek-reasoner` - 增强推理模型

**定价：** 成本远低于 Claude，预算友好的优选

#### Google Gemini - 快速高效

```yaml
llm:
  provider: gemini
  model: gemini-2.0-flash-exp # 可选，未设置则使用默认值
```

**可用模型：**

- `gemini-2.0-flash-exp` - 最新 Gemini 2.0 Flash（默认）
- `gemini-pro` - Gemini Pro 模型

**定价：** 提供免费额度，生产环境性价比高

#### xAI Grok - 高级推理

```yaml
llm:
  provider: grok
  model: grok-beta # 可选，未设置则使用默认值
```

**可用模型：**

- `grok-beta` - 最新 Grok 模型（默认）

**定价：** 价格有竞争力，具有高级推理能力

#### OpenAI - 行业标准

```yaml
llm:
  provider: openai
  model: gpt-4o # 可选，未设置则使用默认值
```

**可用模型：**

- `gpt-4o` - GPT-4 优化版（默认）- 快速且强大
- `gpt-4-turbo` - GPT-4 Turbo - 更强大
- `gpt-3.5-turbo` - GPT-3.5 - 最具性价比

**定价：** $2.50 输入 / $10 输出 每百万 token（GPT-4o）

#### 选择提供商

| 提供商       | 优点                 | 最适合               |
| ------------ | -------------------- | -------------------- |
| **Claude**   | 质量优秀，可靠       | 生产环境，高质量输出 |
| **DeepSeek** | 成本极低，中文支持好 | 预算有限，中文内容   |
| **Gemini**   | 快速，有免费额度     | 大批量，成本优化     |
| **Grok**     | 高级推理，实时数据   | 复杂分析，最新信息   |
| **OpenAI**   | 行业标准，经过验证   | 通用目的，可靠质量   |

### 语言配置

**工作原理：**

- 提示词始终使用**英文**（最适合 Claude 理解）
- 输出可以是 **13+ 种语言**（自动翻译）
- 在 `.env` 或 GitHub Secrets 中设置 `AI_RESPONSE_LANGUAGE`

**支持的语言：**

`en`（English）• `zh`（中文）• `es`（Español）• `fr`（Français）• `ja`（日本語）• `de`（Deutsch）• `ko`（한국어）• `pt`（Português）• `ru`（Русский）• `ar`（العربية）• `hi`（हिन्दी）• `it`（Italiano）• `nl`（Nederlands）

**使用方法：**

```bash
# .env 文件 - 单一语言
AI_RESPONSE_LANGUAGE=zh  # 完整中文输出

# .env 文件 - 多语言（逗号分隔）
AI_RESPONSE_LANGUAGE=en,zh,ja  # 生成英语、中文和日语新闻

# GitHub Secret
# 添加：AI_RESPONSE_LANGUAGE = zh
# 或多语言：AI_RESPONSE_LANGUAGE = en,zh,ja
```

**示例输出（中文）：**

```
国际新闻：

1. OpenAI发布GPT-5增强推理能力
OpenAI发布了GPT-5...
来源：OpenAI官方博客
```

系统会自动添加："IMPORTANT: Please respond entirely in Chinese (中文)" 到提示词中。

## GitHub Actions 设置

项目包含一个 GitHub Actions 工作流，默认在每天 UTC 时间 00:00（北京时间 08:00）运行。

> **重要**：GitHub Actions 使用**仓库 Secrets** 进行配置（不是环境变量）。所有设置都必须添加为 secrets。

### 步骤 1：添加 GitHub 仓库 Secrets

导航到您的 GitHub 仓库：

```
仓库 → Settings → Secrets and variables → Actions → Repository secrets → New repository secret
```

逐个添加以下 secrets：

#### ✅ 必需的 Secrets

| Secret 名称            | 示例值                 | 描述                                       |
| ---------------------- | ---------------------- | ------------------------------------------ |
| `LLM_PROVIDER`         | `claude` 或 `deepseek` | LLM 提供商（默认：`claude`）               |
| `ANTHROPIC_API_KEY`    | `sk-ant-api03-xxx...`  | 您的 Anthropic API 密钥（使用 Claude 时）  |
| `DEEPSEEK_API_KEY`     | `sk-xxx...`            | 您的 DeepSeek API 密钥（使用 DeepSeek 时） |
| `NOTIFICATION_METHODS` | `email,webhook`        | 通知渠道（逗号分隔）                       |

#### 📧 邮件 Secrets（如果使用邮件通知）

| Secret 名称          | 示例值                  | 描述                                                                        |
| -------------------- | ----------------------- | --------------------------------------------------------------------------- |
| `GMAIL_ADDRESS`      | `you@gmail.com`         | 您的 Gmail 邮箱地址                                                         |
| `GMAIL_APP_PASSWORD` | `xxxx xxxx xxxx xxxx`   | Gmail 应用专用密码（[点击获取](https://myaccount.google.com/apppasswords)） |
| `EMAIL_TO`           | `recipient@example.com` | 收件人邮箱地址                                                              |

#### 🔗 Webhook Secrets（如果使用 webhook 通知）

| Secret 名称   | 示例值                        | 描述                  |
| ------------- | ----------------------------- | --------------------- |
| `WEBHOOK_URL` | `https://hooks.slack.com/...` | 您的 webhook 端点 URL |

#### 🌍 可选的 Secrets

| Secret 名称            | 示例值                     | 描述                                                       |
| ---------------------- | -------------------------- | ---------------------------------------------------------- |
| `AI_RESPONSE_LANGUAGE` | `zh` 或 `es` 或 `en,zh,ja` | 语言代码（默认 `en`）。多语言用逗号分隔                    |

### 步骤 2：启用 GitHub Actions

确保在仓库设置中启用了 GitHub Actions：

```
仓库 → Settings → Actions → General → Allow all actions and reusable workflows
```

### 步骤 3：手动触发（测试设置）

配置好 secrets 后，测试您的设置：

```
仓库 → Actions 标签 → Daily AI News Digest → Run workflow 按钮
```

这将立即运行工作流，以便您验证一切正常工作。

### 步骤 4：自定义调度（可选）

工作流默认在每天 UTC 时间午夜运行。要更改调度，编辑 `.github/workflows/daily-news.yml`：

```yaml
schedule:
  - cron: "0 0 * * *" # 每天 UTC 午夜（当前）
  - cron: "0 9 * * *" # 每天 UTC 9:00
  - cron: "0 */6 * * *" # 每 6 小时
```

使用 [crontab.guru](https://crontab.guru/) 创建自定义调度。

## 项目结构

```
ai-news-bot/
├── .github/
│   └── workflows/
│       └── daily-news.yml           # GitHub Actions 工作流
├── src/
│   ├── __init__.py
│   ├── config.py                    # 配置管理
│   ├── logger.py                    # 日志工具
│   ├── news_generator.py            # 新闻生成编排
│   ├── news_fetcher.py              # 分级 RSS/Atom + Google News 获取
│   ├── history.py                   # 跨运行"已报道"记忆
│   ├── llm_providers/
│   │   ├── __init__.py
│   │   ├── base_provider.py         # LLM 提供商基础接口
│   │   ├── claude_provider.py       # Anthropic Claude 提供商
│   │   └── deepseek_provider.py     # DeepSeek 提供商
│   └── notifiers/
│       ├── __init__.py
│       ├── email_notifier.py        # 邮件通知
│       └── webhook_notifier.py      # Webhook 通知
├── main.py                          # 主应用入口
├── config.yaml                      # 活动配置文件
├── requirements.txt                 # Python 依赖
├── .env.example                     # 示例环境变量
├── .gitignore
├── README.md
└── README.zh.md                     # 中文文档
```

## 使用示例

### 仅邮件

```env
NOTIFICATION_METHODS=email
```

### 仅 Webhook

```env
NOTIFICATION_METHODS=webhook
```

### 邮件和 Webhook

```env
NOTIFICATION_METHODS=email,webhook
```

## 邮件格式

### 精美的邮件友好设计

机器人生成**邮件优化的内容**，在所有邮件客户端中都显示精美：

**功能：**

- ✅ 无 markdown 格式（简洁、专业的外观）
- ✅ 自动 HTML 转换，带精美样式
- ✅ 带视觉徽章的编号新闻卡片
- ✅ 颜色编码的章节和标题
- ✅ 移动端响应式布局
- ✅ 支持 Gmail、Outlook、Apple Mail 和所有移动应用

**收件人看到的：**

- 带专业样式的简洁白色容器
- 带微妙边框的蓝色章节标题
- 样式化卡片中的编号新闻项
- 斜体来源引用
- 在任何设备上都舒适的阅读体验

**邮件示例截图：**

<div align="center">

| 中文邮件 | 英文邮件 |
|:-------------:|:-------------:|
| ![中文 AI 新闻摘要](image/screenshot1.png) | ![英文 AI 新闻摘要](image/screenshot2.png) |
| 中文版新闻摘要 | 英文版新闻摘要 |

</div>

**预览您的邮件：**
在本地运行机器人并检查生成的 HTML 邮件内容。

## 邮件设置指南

Gmail SMTP 是发送邮件最简单的方式 - 只需使用您现有的 Gmail 账户！

### 步骤 1：启用两步验证

1. 访问 [Google 账户安全设置](https://myaccount.google.com/security)
2. 点击 **两步验证**
3. 按照提示启用（应用专用密码需要此功能）

### 步骤 2：创建应用专用密码

1. 访问 [Google 应用专用密码](https://myaccount.google.com/apppasswords)
   - 或者：Google 账户 → 安全性 → 两步验证 → 应用专用密码
2. 选择应用：**邮件**
3. 选择设备：**其他**（输入 "AI News Bot"）
4. 点击 **生成**
5. 复制 16 位密码（格式如：`xxxx xxxx xxxx xxxx`）

> ⚠️ **重要**：这不是您的普通 Gmail 密码。请妥善保管此应用专用密码！

### 步骤 3：配置环境变量

```env
# Gmail 配置
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_TO=recipient@example.com
NOTIFICATION_METHODS=email
```

就这样！您的 Gmail 已准备好发送新闻摘要。

### Gmail 故障排除

- **"认证失败"**：确保使用的是应用专用密码，而非普通密码
- **"不安全的应用"**：这是过时的方式，请改用应用专用密码
- **找不到应用专用密码**：您必须先启用两步验证

## Webhook 集成

Webhook 发送 JSON 负载：

```json
{
  "title": "AI News Digest - 2025-10-25",
  "content": "... 新闻摘要内容 ...",
  "timestamp": "2025-10-25T09:00:00",
  "source": "AI News Bot"
}
```

兼容：

- Slack（使用 Incoming Webhooks）
- Discord（使用 Webhook URLs）
- Microsoft Teams
- 自定义 webhook 端点

## 错误处理

- **自动重试**：新闻生成器在失败时最多重试 3 次
- **优雅降级**：如果一种通知方式失败，其他方式仍会执行
- **全面日志**：所有操作都带有时间戳和上下文记录
- **GitHub Actions 工件**：上传错误日志以便调试

## 故障排除

### "Config file not found" 错误

确保 `config.yaml` 存在于项目根目录。

### 邮件未发送

- 确保使用的是**应用专用密码**，而非普通 Gmail 密码
- 验证您的 Google 账户已启用两步验证
- 检查 `GMAIL_ADDRESS` 和 `GMAIL_APP_PASSWORD` 设置正确
- 应用专用密码应为 16 个字符（有无空格均可）

### Webhook 失败

- 验证 webhook URL 可访问
- 检查 webhook 端点接受 JSON POST 请求
- 查看 webhook 服务日志

### API 错误

- 验证 `ANTHROPIC_API_KEY` 有效
- 检查 API 配额/速率限制
- 查看 Anthropic API 状态

## 开发

### 运行测试（如果可用）

```bash
pytest
```

### 本地开发

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows 上：venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行机器人
python main.py
```

## 许可证

GPL-3.0 许可证 - 详见 LICENSE 文件

## 支持

- **Discord 社区**：加入我们的 [Discord 服务器](https://discord.gg/AtfQPh8T2T) 进行讨论、获取支持和了解更新
- **GitHub Issues**：报告 bug 和功能请求，请使用 [GitHub issue 跟踪器](https://github.com/giftedunicorn/ai-news-bot/issues)

## 致谢

由以下技术提供支持：

- [Anthropic Claude](https://www.anthropic.com)
- [DeepSeek](https://www.deepseek.com)

---

## ⭐ Star 历史

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=giftedunicorn/ai-news-bot&type=Date)](https://star-history.com/#giftedunicorn/ai-news-bot&Date)

</div>

---

<div align="center">

**[⬆ 返回顶部](#ai-新闻机器人)**

用 ❤️ 由开源社区打造

</div>
