---
name: image-recognition
description: 图像识别（非 OCR）。当用户提供图片并希望提取/识别图片中的全部内容——如截图、文档扫描件、图表、表格、海报、界面、照片等——并将其整理为排版一致的 Markdown 文本时使用。流程：将图片缩放至最长边 ≤1280px，通过本地视觉大模型 API（OpenAI 兼容 /v1/chat/completions）识别，返回 Markdown。触发词：识别图片、看图、识图、图片转 Markdown、提取图片内容、读取图片信息。
agent_created: true
---

# Image Recognition（图像识别，非 OCR）

## Overview

本技能将图片内容转为 Markdown 文本。与 OCR 不同，它调用**本地视觉大模型**（VLM，如 Ollama 的 qwen2.5vl / llava）理解整张图片的语义内容（图表、布局、表格、界面等），并保持排版一致地输出 Markdown。

核心脚本：`scripts/recognize_image.py`（自动完成缩放 → Base64 编码 → 调用本地 API → 输出 Markdown）。

## 工作流程

1. **确认图片路径**：用户提供图片（直接路径或附件），必要时先复制到本地绝对路径。
2. **准备 Python 环境**：使用主目录（项目根目录）venv 的 Python 解释器：
   - `E:\ImageSkill\venv\Scripts\python.exe`（Windows）——存在则直接使用；
   - 不存在时用托管 Python 创建：`python -m venv E:\ImageSkill\venv`，并安装依赖 `pip install pillow requests`。
   - 统一用该 venv 执行本技能脚本及后续 Python 代码。
3. **运行识别脚本**（Windows 下用完整路径，避免编码问题）：
   ```bash
   "E:\ImageSkill\venv\Scripts\python.exe" "<skill>/scripts/recognize_image.py" "<图片路径>" --output "<临时输出.md>"
   ```
   - 脚本将图片缩放（最长边 ≤1280px）、编码为 data URI，POST 到 `{api_base}/v1/chat/completions`。
   - 模型名缺省时自动通过 `/v1/models` 探测视觉模型（优先含 vl/vision/llava 等关键词者）。
   - `--output` 将 Markdown 写入文件（避免控制台编码问题），同时打印到标准输出。
4. **获取 Markdown 并提供给会话**：读取输出文件内容，直接呈现给用户，并说明可用于后续操作（如转文档、再编辑、总结等）。

## 配置

配置优先级：**命令行参数 > 环境变量 > `config.json` > 内置默认值**。

- API 地址（关键）：`config.json` 的 `api_base`，或环境变量 `VISION_API_BASE`，或 `--api-base`。默认 `http://127.0.0.1:11434`（Ollama）。脚本自动拼接 `/v1/chat/completions`。
- 模型：环境变量 `VISION_MODEL` / `--model`；留空则自动探测。
- 提示词：默认「识别图片里所有信息，使用 markdown 输出全部内容，并保持排版的一致」，可用 `--prompt` / `VISION_PROMPT` 覆盖。
- 其他：`--max-size`（默认 1280）、`--max-tokens`（默认 4096）、`--timeout`（默认 600s）。

## 常用命令示例

```bash
# 基本识别（自动探测模型）
"E:\ImageSkill\venv\Scripts\python.exe" recognize_image.py "C:\tmp\shot.png"

# 指定模型 + 保存结果
"E:\ImageSkill\venv\Scripts\python.exe" recognize_image.py "C:\tmp\chart.png" --model qwen2.5vl:7b --output "C:\tmp\chart.md"

# 仅自检图片预处理（不调用 API）
"E:\ImageSkill\venv\Scripts\python.exe" recognize_image.py "C:\tmp\shot.png" --dry-run
```

## 故障排查

- **Connection refused / 超时**：本地视觉服务未启动。引导用户启动服务：Ollama 需运行 `ollama serve`（或打开应用）；LM Studio 需在 Server 页启用服务。
- **HTTP 4xx/5xx**：检查 API 地址与端口是否正确（Ollama 11434 / LM Studio 1234 / vLLM 8000）。
- **「未找到可用模型」**：服务已启动但无模型或非视觉模型。用 `--model` 指定模型名；Ollama 可执行 `ollama pull qwen2.5vl` 拉取视觉模型。
- **图片过大**：脚本已自动缩放至最长边 ≤1280px；若 API 仍报错，可调小 `--max-size`。

## Resources

- `scripts/recognize_image.py` — 主识别脚本（缩放/编码/调用/输出）。
- `config.json` — 默认配置（api_base、model、prompt 等）。
