"""
AI 客户端：兼容 OpenAI / DeepSeek / 本地 Ollama 等所有
"OpenAI 兼容"协议的接口。通过配置 base_url / api_key / model 切换。
"""

import requests
import json


class AIError(Exception):
    pass


class AIClient:
    def __init__(self, cfg: dict):
        ai = cfg or {}
        self.base_url = (ai.get("base_url") or "").strip().rstrip("/")
        self.api_key = (ai.get("api_key") or "").strip()
        self.model = (ai.get("model") or "deepseek-chat").strip()
        self.temperature = float(ai.get("temperature", 0.7))
        self.timeout = int(ai.get("timeout", 180))
        self.enabled = bool(ai.get("enabled", False))

    def _endpoint(self) -> str:
        # 兼容 /v1 结尾与根地址
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    def is_ready(self) -> tuple:
        """返回 (是否可用, 提示)"""
        if not self.enabled:
            return False, "AI 功能未启用，请先在「设置」中填写 API 配置"
        if not self.api_key:
            return False, "未填写 API Key"
        if not self.base_url:
            return False, "未填写 API 地址"
        return True, ""

    def chat(self, messages: list, temperature: float = None) -> str:
        ok, msg = self.is_ready()
        if not ok:
            raise AIError(msg)
        url = self._endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "stream": False,
        }
        try:
            resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
        except requests.exceptions.Timeout:
            raise AIError(f"请求超时（{self.timeout}s），请检查网络或增大超时时间")
        except requests.exceptions.ConnectionError:
            raise AIError(f"无法连接 {self.base_url}，请检查网络与地址")
        except Exception as e:
            raise AIError(f"请求失败: {e}")

        if resp.status_code != 200:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except Exception:
                detail = resp.text[:300]
            raise AIError(f"HTTP {resp.status_code}: {detail}")

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception:
            raise AIError("返回格式异常，未解析到文本内容")

    def test(self) -> str:
        """发送一个最小请求测试连通性"""
        return self.chat([{"role": "user", "content": "请只回复两个字：正常"}])


DEFAULT_PROVIDERS = [
    {
        "name": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "default": True,
    },
    {
        "name": "openai",
        "label": "OpenAI (GPT)",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "default": False,
    },
    {
        "name": "moonshot",
        "label": "Kimi (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "default": False,
    },
    {
        "name": "ollama",
        "label": "本地 Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
        "default": False,
    },
]
