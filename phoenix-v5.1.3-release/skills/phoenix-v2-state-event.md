---
name: phoenix-v2-state-event
description: "Phoenix V5.1状态管理 — AppState/事件流/GC/健康摘要"
---
# Phoenix V5.1 状态管理

## AppState
全局状态对象，管理：
- 熔断器状态
- 任务队列
- 内存使用

## 事件流
状态变更事件记录，支持：
- 实时监控
- 历史回放
- 问题追溯
