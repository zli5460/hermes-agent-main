"""
Phoenix V8 — 故障处理卡（Fault Playbook）
来源: 主控Agent投喂手册V7 附录B

4类常见故障的标准处理流程，Agent遇到对应故障时按流程执行。
"""

from typing import Dict, List, Optional
from datetime import datetime


class FaultPlaybook:
    """
    故障快速处理卡
    
    4类标准故障的处理流程：
    1. 记忆文件加载失败或内容丢失
    2. 定时任务未按时执行
    3. 外部API调用失败
    4. 文件权限不足
    """
    
    PLAYBOOKS = {
        "memory_failure": {
            "name": "记忆文件加载失败或内容丢失",
            "triggers": ["memory", "记忆", "加载失败", "内容丢失", "文件为空", "文件损坏"],
            "steps": [
                {"step": 1, "action": "确认核心文件完整性", "command": "cat {root}/SOUL.md | head -5"},
                {"step": 2, "action": "查看记忆文件实际内容", "command": "cat {root}/MEMORY.md | head -20"},
                {"step": 3, "action": "检查文件大小和修改时间", "command": "ls -la {root}/*.md"},
                {"step": 4, "action": "如果为空或损坏→触发时机3汇报", "rule": "不得自行重建内容"},
            ],
            "report_format": "发现异常：记忆文件{file}加载失败。已尝试：检查文件完整性和内容。需要用户指示是否重建。",
        },
        "cron_failure": {
            "name": "定时任务未按时执行",
            "triggers": ["cron", "定时", "调度", "heartbeat", "心跳"],
            "steps": [
                {"step": 1, "action": "确认任务还在crontab中", "command": "crontab -l"},
                {"step": 2, "action": "检查进程是否还在运行", "command": "ps aux | grep {task_name}"},
                {"step": 3, "action": "查看任务日志", "command": "tail -50 {root}/logs/{task_name}.log"},
                {"step": 4, "action": "如果进程卡死→汇报并等授权kill", "rule": "不得自行kill进程"},
            ],
            "report_format": "发现异常：定时任务{task}未按时执行。已尝试：检查crontab和进程状态。需要用户授权处理。",
        },
        "api_failure": {
            "name": "外部API调用失败",
            "triggers": ["api", "API", "请求失败", "超时", "连接", "502", "503"],
            "steps": [
                {"step": 1, "action": "记录原始报错信息（不得篡改）", "rule": "保存原始错误文本"},
                {"step": 2, "action": "判断：网络问题还是API本身问题", "command": "curl -s -o {null} -w '%{{http_code}}' {api_url}", "null": "NUL" if __import__('platform').system() == 'Windows' else "/dev/null"},
                {"step": 3, "action": "重试1次，仍失败则暂停所有依赖任务", "rule": "只重试1次"},
                {"step": 4, "action": "触发时机3汇报，告知影响范围", "rule": "说明哪些任务受影响"},
            ],
            "report_format": "发现异常：外部API{api}调用失败。错误：{error}。已尝试：重试1次仍失败。影响范围：{affected_tasks}。",
        },
        "permission_failure": {
            "name": "文件权限不足",
            "triggers": ["permission", "权限", "denied", "forbidden", "403"],
            "steps": [
                {"step": 1, "action": "记录具体报错信息", "rule": "保存原始错误"},
                {"step": 2, "action": "不得自行chmod或sudo", "rule": "这是P0操作"},
                {"step": 3, "action": "触发权限申请（P0流程）", "rule": "等待用户授权"},
                {"step": 4, "action": "记录处理结果到MEMORY.md", "rule": "常固化"},
            ],
            "report_format": "权限申请：需要执行{operation}。操作详情：{command}。原因：{reason}。风险：{risk}。回滚方案：{rollback}。请问是否授权？",
        },
    }

    def __init__(self, root: str = "~"):
        self._root = root
        self._execution_log: List[Dict] = []

    def match_fault(self, error_message: str) -> Optional[Dict]:
        """根据错误信息匹配故障类型"""
        error_lower = error_message.lower()
        best_match = None
        best_score = 0
        
        for fault_id, playbook in self.PLAYBOOKS.items():
            score = sum(1 for t in playbook["triggers"] if t.lower() in error_lower)
            if score > best_score:
                best_score = score
                best_match = {"id": fault_id, **playbook}
        
        return best_match if best_score > 0 else None

    def get_steps(self, fault_id: str) -> List[Dict]:
        """获取故障处理步骤"""
        playbook = self.PLAYBOOKS.get(fault_id)
        if not playbook:
            return []
        return playbook["steps"]

    def get_report_format(self, fault_id: str, **kwargs) -> str:
        """获取汇报格式模板"""
        playbook = self.PLAYBOOKS.get(fault_id)
        if not playbook:
            return ""
        try:
            return playbook["report_format"].format(**kwargs)
        except KeyError:
            return playbook["report_format"]

    def execute_step(self, fault_id: str, step_num: int, result: str = ""):
        """记录步骤执行结果"""
        self._execution_log.append({
            "fault_id": fault_id,
            "step": step_num,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        })

    def get_execution_log(self) -> List[Dict]:
        """获取执行日志"""
        return self._execution_log.copy()

    def list_faults(self) -> List[Dict]:
        """列出所有支持的故障类型"""
        return [
            {"id": fid, "name": p["name"], "trigger_count": len(p["triggers"])}
            for fid, p in self.PLAYBOOKS.items()
        ]
