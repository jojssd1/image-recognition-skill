#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recognize_image.py —— 图像识别（非 OCR）

将图片缩放（最长边 <= 1280px）后，通过本地视觉大模型 API
（OpenAI 兼容 /v1/chat/completions）识别图片内容，输出排版一致的 Markdown 文本。

用法:
  python recognize_image.py <图片路径> [选项]

选项:
  --prompt TEXT    识别提示词（优先级最高，覆盖预设）
  --prompt-key KEY  使用 config.json 中 prompts 预设的提示词模板，
                   如 photo / animal / plant / food / scene / chart / document
  --api-base URL   API 基础地址，自动拼接 /v1/chat/completions
                   （默认: config.json 的 api_base 或环境变量 VISION_API_BASE）
  --model NAME     模型名；缺省时自动从 /v1/models 探测视觉模型
                   （可设环境变量 VISION_MODEL）
  --max-size N     最长边像素上限，默认 1280
  --max-tokens N   生成上限，默认 4096
  --output FILE    将 Markdown 写入文件（同时仍会打印到标准输出）
  --dry-run        仅执行图片预处理，不调用 API（用于自检）
  --timeout SEC    请求超时秒数，默认 600

配置优先级: 命令行 > 环境变量 > config.json（本脚本同目录）> 内置默认值

示例:
  python recognize_image.py shot.png
  python recognize_image.py shot.png --model qwen2.5vl:7b --output result.md
"""

import argparse
import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Windows 控制台可能不是 UTF-8，统一重配置为标准 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DEFAULT_PROMPT = "识别图片里所有信息，使用 markdown 输出全部内容，并保持排版的一致"
DEFAULT_API_BASE = "http://127.0.0.1:11434"  # Ollama 默认端口

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / "config.json"


def safe_remove(path):
    """容错删除临时文件：部分沙箱/回收站不可用环境下 os.remove 可能抛错，
    临时文件残留无害，忽略即可。"""
    try:
        os.remove(path)
    except OSError:
        pass


def load_config() -> dict:
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[warn] 配置文件解析失败({CONFIG_FILE}): {e}", file=sys.stderr)
    return cfg if isinstance(cfg, dict) else {}


def resolve_settings(args) -> dict:
    cfg = load_config()
    api_base = (args.api_base
                or os.environ.get("VISION_API_BASE")
                or cfg.get("api_base")
                or DEFAULT_API_BASE)
    model = (args.model
             or os.environ.get("VISION_MODEL")
             or cfg.get("model")
             or "")
    prompts_cfg = cfg.get("prompts") or {}
    preset_prompt = prompts_cfg.get(args.prompt_key) if args.prompt_key else None
    prompt = (args.prompt
              or preset_prompt
              or os.environ.get("VISION_PROMPT")
              or cfg.get("prompt")
              or prompts_cfg.get("default")
              or DEFAULT_PROMPT)
    return {
        "api_base": api_base.rstrip("/"),
        "model": model,
        "prompt": prompt,
        "prompt_key": args.prompt_key,
        "max_size": args.max_size,
        "max_tokens": args.max_tokens,
        "timeout": args.timeout,
    }


def prepare_image(image_path: str, max_size: int):
    """缩放图片（最长边 <= max_size），返回 (临时文件路径, 图片格式)。"""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("缺少依赖 Pillow，请安装: pip install pillow", file=sys.stderr)
        sys.exit(2)

    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)  # 修正 EXIF 旋转

    # 统一为 RGB（透明背景垫白，避免 PNG 通道问题）
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "RGBA":
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img.convert("RGB"))
        img = bg
    else:
        img = img.convert("RGB")

    w, h = img.size
    longest = max(w, h)
    scale = 1.0
    if longest > max_size:
        scale = max_size / longest
        new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    tmpdir = SCRIPT_DIR / "tmp"
    tmpdir.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".png", dir=tmpdir)
    os.close(fd)
    img.save(tmp, "PNG")
    fmt = "png"

    # 体积过大时转 JPEG 压缩（data URI 过大会超出多数服务限制）
    if os.path.getsize(tmp) > 10 * 1024 * 1024:
        fd2, tmp2 = tempfile.mkstemp(suffix=".jpg", dir=tmpdir)
        os.close(fd2)
        img.save(tmp2, "JPEG", quality=88)
        safe_remove(tmp)
        tmp, fmt = tmp2, "jpeg"

    return tmp, fmt, (w, h, img.size[0], img.size[1])


def detect_model(api_base: str, timeout: int = 10):
    """通过 /v1/models 探测可用模型，优先返回视觉模型。"""
    try:
        import requests
        r = requests.get(f"{api_base}/v1/models", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        models = [m.get("id") or m.get("name") for m in data.get("data", [])]
        models = [m for m in models if m]
        if not models:
            return None
        vision_keys = ("vl", "vision", "llava", "vlm", "minicpm",
                       "glm-4v", "internvl", "qwen2-vl", "qwen2.5-vl", "moondream")
        for m in models:
            low = m.lower()
            if any(k in low for k in vision_keys):
                return m
        return models[0]  # 未识别出视觉模型时退回第一个
    except Exception as e:
        print(f"[warn] 模型探测失败({api_base}/v1/models): {e}", file=sys.stderr)
        return None


def call_vision_api(settings: dict, image_path: str):
    import requests
    tmp, fmt, dims = prepare_image(image_path, settings["max_size"])
    try:
        with open(tmp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        data_uri = f"data:image/{fmt};base64,{b64}"

        model = settings["model"] or detect_model(settings["api_base"])
        if not model:
            print("未找到可用模型：请用 --model 指定模型名，或先启动本地视觉服务并拉取视觉模型"
                  "（如 ollama pull qwen2.5vl）", file=sys.stderr)
            sys.exit(3)

        url = f"{settings['api_base']}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": settings["prompt"]},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }],
            "temperature": 0.1,
            "max_tokens": settings["max_tokens"],
        }
        started = time.time()
        r = requests.post(url, json=payload, timeout=settings["timeout"])
        elapsed = time.time() - started
        if r.status_code != 200:
            detail = ""
            try:
                detail = json.dumps(r.json(), ensure_ascii=False)
            except Exception:
                detail = r.text[:500]
            print(f"API 调用失败 HTTP {r.status_code}: {detail}", file=sys.stderr)
            sys.exit(4)
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):  # 部分服务返回分段内容
            content = "".join(
                seg.get("text", "") if isinstance(seg, dict) else str(seg)
                for seg in content
            )
        print(f"[info] api={settings['api_base']} model={model} "
              f"原尺寸={dims[0]}x{dims[1]} 发送尺寸={dims[2]}x{dims[3]} "
              f"耗时={elapsed:.1f}s 提示词={'[' + settings['prompt_key'] + ']' if settings['prompt_key'] else '自定义'}", file=sys.stderr)
        return content
    finally:
        safe_remove(tmp)


def main():
    parser = argparse.ArgumentParser(
        description="图像识别（非 OCR）：调用本地视觉 API 输出 Markdown")
    parser.add_argument("image", help="图片路径")
    parser.add_argument("--prompt", help="识别提示词（最高优先级）")
    parser.add_argument("--prompt-key", choices=None,
                        help="config.json 中 prompts 预设模板名，如 photo/animal/plant/food/scene/chart/document")
    parser.add_argument("--api-base", help="API 基础地址（自动拼接 /v1/chat/completions）")
    parser.add_argument("--model", help="模型名（缺省自动探测）")
    parser.add_argument("--max-size", type=int, default=1280, help="最长边上限（默认 1280）")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--output", help="Markdown 输出文件路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预处理图片，不调用 API")
    parser.add_argument("--timeout", type=int, default=600, help="请求超时（秒）")
    args = parser.parse_args()

    if not os.path.isfile(args.image):
        print(f"图片不存在: {args.image}", file=sys.stderr)
        sys.exit(2)

    settings = resolve_settings(args)

    if args.dry_run:
        tmp, fmt, dims = prepare_image(args.image, settings["max_size"])
        try:
            print(f"[dry-run] 原尺寸={dims[0]}x{dims[1]} 发送尺寸={dims[2]}x{dims[3]} "
                  f"格式={fmt} 大小={os.path.getsize(tmp)//1024}KB "
                  f"api_base={settings['api_base']} 提示词={settings['prompt'][:40]}...")
        finally:
            safe_remove(tmp)
        return

    markdown = call_vision_api(settings, args.image)
    sys.stdout.write(markdown)
    sys.stdout.write("\n")
    sys.stdout.flush()
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(f"[info] 已保存到 {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
