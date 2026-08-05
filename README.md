# image-recognition-skill

AI 图像识别 Skill（非 OCR）—— 将图片内容转为排版一致的 Markdown。

调用**本地视觉大模型**（VLM），把图片缩放后发送给 OpenAI 兼容的 `/v1/chat/completions` 接口，返回完整内容的 Markdown 文本。适用于截图、文档扫描件、图表、表格、海报、界面等图片的语义识别。

## 特性

- ✅ 自动缩放：最长边 ≤ 1280px（LANCZOS，自动修正 EXIF 旋转、透明底垫白）
- ✅ 本地推理：图片不上传云端，隐私安全
- ✅ 自动探测模型：未指定模型时通过 `/v1/models` 自动选择视觉模型
- ✅ 可配置：API 地址 / 模型 / 提示词支持命令行、环境变量、配置文件三级覆盖

## 目录结构

```
image-recognition/
├── SKILL.md               # 技能定义（触发词 + 使用流程）
├── config.json            # 默认配置（api_base / model / prompt）
└── scripts/
    └── recognize_image.py # 核心脚本：缩放 → 编码 → 调用 API → 输出 Markdown
```

## 安装（WorkBuddy / Agent Skills 规范）

把 `image-recognition` 整个文件夹复制到技能目录即可：

- **WorkBuddy（用户级）**：`~/.workbuddy/skills/`
- 其他遵循 Agent Skills 规范的应用：复制到其 skills 目录

## 依赖

1. **本地视觉服务**：Ollama（推荐）、LM Studio 或任意 OpenAI 兼容服务，默认地址 `http://127.0.0.1:11434`
2. **视觉模型**：`qwen2.5vl:3b`（轻量，4~6GB 显存可流畅运行）或更大模型，安装：`ollama pull qwen2.5vl:3b`
3. **Python 环境**：Python 3.10+，安装依赖：`pip install pillow requests`

## 使用

```bash
# 基本识别（自动探测模型）
python recognize_image.py "图片路径"

# 指定模型并保存结果
python recognize_image.py "图片路径" --model qwen2.5vl:3b --output result.md

# 仅自检图片预处理（不调用 API）
python recognize_image.py "图片路径" --dry-run
```

配置优先级：**命令行参数 > 环境变量 > config.json > 默认值**。

| 配置项 | 环境变量 | 默认值 |
| --- | --- | --- |
| API 地址 | `VISION_API_BASE` | `http://127.0.0.1:11434` |
| 模型名 | `VISION_MODEL` | 自动探测 |
| 提示词 | `VISION_PROMPT` | 识别图片里所有信息，使用 markdown 输出全部内容，并保持排版的一致 |

## 示例

输入一张销售报表截图，输出：

```markdown
2026年7月销售报告

| 产品 | 销量(件) | 销售额(元) |
| --- | --- | --- |
| A 型号 | 1200 | 96,000 |
| B 型号 | 860 | 77,400 |
| C 型号 | 540 | 59,400 |

1. 华南区销售额环比增长 12%
2. 华东区新签约客户 45 家
3. 新品上市准备中
```

## 故障排查

- **Connection refused**：本地视觉服务未启动，运行 `ollama serve`
- **未找到可用模型**：`--model` 指定模型名，或先 `ollama pull qwen2.5vl`
- **图片过大报错**：调小 `--max-size`（默认 1280）

## License

MIT
