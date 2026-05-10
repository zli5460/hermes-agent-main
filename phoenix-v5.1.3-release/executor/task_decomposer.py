"""
Phoenix V5.1 任务分解器 + 三轮自验证
V4.7: 基于复杂度和预估执行时间判断是否需要分解
V4.6: 新增三轮自验证机制（来源：主控Agent投喂手册V7）
"""

import re
from typing import List, Dict, Optional

# 各类任务的预估执行时间（分钟）
TASK_TIME_ESTIMATE = {
    "code_small": 1,
    "code_medium": 3,
    "code_large": 8,
    "reasoning_light": 0.5,
    "reasoning": 5,
    "document": 2,
    "analysis": 4,
    "simple": 0.5,
}

# 分解阈值（分钟）
DECOMPOSE_THRESHOLD = 5

# 模型推荐
MODEL_MAP = {
    "code_small": "xiaomi/mimo-v2.5",
    "code_medium": "anthropic/claude-sonnet-4.6",
    "code_large": "anthropic/claude-opus-4.7",
    "reasoning_light": "xiaomi/mimo-v2.5",
    "reasoning": "anthropic/claude-opus-4.7",
    "document": "xiaomi/mimo-v2.5",
    "analysis": "anthropic/claude-opus-4.7",
    "simple": "xiaomi/mimo-v2.5",
}


def classify_subtask(task: str) -> str:
    """分类子任务类型"""
    task_lower = task.lower()
    
    if any(kw in task_lower for kw in ["写代码", "爬虫", "API", "函数", "脚本", "程序", "代码"]):
        if any(kw in task_lower for kw in ["简单", "小", "hello", "demo"]):
            return "code_small"
        elif any(kw in task_lower for kw in ["架构", "系统", "微服务", "重构"]):
            return "code_large"
        else:
            return "code_medium"
    
    if any(kw in task_lower for kw in ["分析", "推理", "研究", "深度", "专业"]):
        if any(kw in task_lower for kw in ["简单", "快速", "大概"]):
            return "reasoning_light"
        else:
            return "reasoning"
    
    if any(kw in task_lower for kw in ["文档", "整理", "总结", "报告"]):
        return "document"
    
    return "simple"


def decompose_task(message: str) -> dict:
    """
    分解复杂任务（基于预估时间）
    
    Returns:
        {"need_decompose": bool, "subtasks": [...], "total_time": float, "reason": str}
    """
    need_decompose = False
    for pattern in [r"\+", r"和", r"以及", r"、", r"，"]:
        if re.search(pattern, message):
            need_decompose = True
            break
    
    if not need_decompose:
        return {"need_decompose": False, "reason": "single_task", "subtasks": [], "total_time": 0}
    
    # V4.7 修复：正确切分"以及"等完整词组
    parts = re.split(r'\s*(?:\+|和|以及|、|，|；)\s*', message)
    # 过滤空白和太短的部分（至少4个字符）
    parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 3]
    
    if len(parts) < 2:
        return {"need_decompose": False, "reason": "cannot_split", "subtasks": [], "total_time": 0}
    
    subtasks = []
    total_time = 0
    for i, part in enumerate(parts):
        task_type = classify_subtask(part)
        model = MODEL_MAP.get(task_type, "xiaomi/mimo-v2.5")
        est_time = TASK_TIME_ESTIMATE.get(task_type, 1)
        total_time += est_time
        subtasks.append({
            "id": i + 1,
            "task": part,
            "model": model,
            "task_type": task_type,
            "est_time": est_time,
            "verification": None,  # V4.6: 三轮自验证结果
        })
    
    if total_time < DECOMPOSE_THRESHOLD:
        return {
            "need_decompose": False,
            "reason": f"total_time_{total_time:.1f}min_below_threshold",
            "subtasks": [],
            "total_time": total_time,
        }
    
    return {
        "need_decompose": True,
        "subtasks": subtasks,
        "reason": f"total_time_{total_time:.1f}min_above_threshold",
        "total_time": total_time,
    }


# ===== V4.6 三轮自验证（来源：主控Agent投喂手册V7） =====

class SelfVerification:
    """
    三轮自验证流程
    
    每个子任务执行后必须经过三轮验证：
    第一轮：意图确认 — 我理解的任务是什么？
    第二轮：执行验证 — 我执行的命令有没有实际输出？
    第三轮：结果核对 — 输出是否回答了原始问题？
    """
    
    @staticmethod
    def verify_round1_intent(task: str, restated_intent: str) -> Dict:
        """第一轮：意图确认 — 用一句话复述任务"""
        # 检查复述是否合理（不是空的，不是原封不动复制）
        if not restated_intent or len(restated_intent) < 5:
            return {"passed": False, "round": 1, "reason": "复述过短或为空"}
        if restated_intent.strip() == task.strip():
            return {"passed": False, "round": 1, "reason": "复述与原文完全相同，未真正理解"}
        return {"passed": True, "round": 1, "intent": restated_intent}
    
    @staticmethod
    def verify_round2_execution(command_output: str, has_command_output: bool = True) -> Dict:
        """第二轮：执行验证 — 命令是否有实际输出"""
        if not has_command_output:
            return {"passed": False, "round": 2, "reason": "无可验证的命令输出"}
        if not command_output or len(command_output.strip()) < 3:
            return {"passed": False, "round": 2, "reason": "命令输出为空或过短"}
        # 检查是否是典型的"假输出"（只有确认语没有实际数据）
        fake_indicators = ["已完成", "搞定了", "成功了", "好的"]
        if any(command_output.strip().startswith(f) for f in fake_indicators):
            return {"passed": False, "round": 2, "reason": "输出只是口头确认，无实际数据"}
        return {"passed": True, "round": 2, "output_length": len(command_output)}
    
    @staticmethod
    def verify_round3_result(expected: str, actual_output: str, tolerance: float = 0.5) -> Dict:
        """第三轮：结果核对 — 对比预期与实际"""
        if not actual_output:
            return {"passed": False, "round": 3, "reason": "无实际输出可对比"}
        
        # 字符级匹配（对中文最友好，不需要分词）
        exp_chars = set(re.findall(r'[\u4e00-\u9fff]', expected))
        act_chars = set(re.findall(r'[\u4e00-\u9fff]', actual_output))
        
        # 英文单词匹配
        exp_words = set(re.findall(r'[a-zA-Z]{3,}', expected.lower()))
        act_words = set(re.findall(r'[a-zA-Z]{3,}', actual_output.lower()))
        
        # 合并计算
        all_expected = exp_chars | exp_words
        all_actual = act_chars | act_words
        
        if not all_expected:
            return {"passed": True, "round": 3, "reason": "无明确预期，跳过对比"}
        
        overlap = len(all_expected & all_actual) / len(all_expected)
        
        if overlap < tolerance:
            return {
                "passed": False, "round": 3,
                "reason": f"匹配度{overlap:.0%}低于阈值{tolerance:.0%}",
            }
        return {"passed": True, "round": 3, "match_rate": f"{overlap:.0%}"}
    
    @staticmethod
    def full_verify(task: str, restated_intent: str, command_output: str,
                    expected: str, actual_output: str) -> Dict:
        """完整三轮验证 — 任一轮失败则整体失败"""
        results = []
        
        r1 = SelfVerification.verify_round1_intent(task, restated_intent)
        results.append(r1)
        if not r1["passed"]:
            return {"passed": False, "failed_round": 1, "results": results, 
                    "action": "重新理解任务并复述"}
        
        r2 = SelfVerification.verify_round2_execution(command_output)
        results.append(r2)
        if not r2["passed"]:
            return {"passed": False, "failed_round": 2, "results": results,
                    "action": "重新执行命令并获取实际输出"}
        
        r3 = SelfVerification.verify_round3_result(expected, actual_output)
        results.append(r3)
        if not r3["passed"]:
            return {"passed": False, "failed_round": 3, "results": results,
                    "action": "检查输出是否回答了原始问题，必要时补充执行"}
        
        return {"passed": True, "results": results, "action": "验证通过，可闭环"}
