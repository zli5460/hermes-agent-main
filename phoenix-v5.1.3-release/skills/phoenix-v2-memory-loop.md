# Phoenix Memory Loop V4.7

## 三层记忆
1. 短期记忆 — 当前会话上下文
2. 事实记忆 — 用户偏好/环境信息（JSON持久化）
3. 长期记忆 — 跨会话知识（session_search）

## 记忆流程
对话 → 提取事实 → 写入facts.json → 下次会话注入system prompt
