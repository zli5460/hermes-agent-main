# Phoenix V8 变更说明

本版本为初心回归版：手动升档 + 自动托底。

- 只认 `/深度` `/大神` `/真神`。
- 禁止自动升档和 hook 假切换。
- OpenAI 兼容端点统一使用 `chat_completions`。
- 每档具备 primary/fallback/emergency。
- API Key 不内置、不明文输出，只通过客户本机 env 引用。
