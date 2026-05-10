#!/usr/bin/env python3
"""Phoenix V4.7 Adapt/Sandbox/Workflow/GitHub模块测试"""

import sys
import os
import tempfile
import unittest
from pathlib import Path

HERMES_DIR = str(Path.home() / ".hermes")
if HERMES_DIR not in sys.path:
    sys.path.insert(0, HERMES_DIR)

class TestAdaptModule(unittest.TestCase):
    """适配器模块测试"""

    def test_import(self):
        import adapt
        self.assertIsNotNone(adapt)

    def test_adapter_loads(self):
        from adapt.adapter import HermesAdapter
        adapter = HermesAdapter()
        self.assertIsNotNone(adapter)

class TestSandboxModule(unittest.TestCase):
    """沙箱模块测试"""

    def test_import(self):
        import sandbox
        self.assertIsNotNone(sandbox)

class TestWorkflowModule(unittest.TestCase):
    """工作流模块测试"""

    def test_import(self):
        import workflow
        self.assertIsNotNone(workflow)

class TestGitHubModule(unittest.TestCase):
    """GitHub模块测试"""

    def test_import(self):
        import github
        self.assertIsNotNone(github)

class TestIntegrationModules(unittest.TestCase):
    """其他集成模块测试"""

    def test_hooks_import(self):
        import integration.hooks
        self.assertTrue(hasattr(integration.hooks, "__file__"))

    def test_startup_import(self):
        import integration.startup
        self.assertTrue(hasattr(integration.startup, "__file__"))

    def test_cron_sync_import(self):
        import integration.cron_sync
        self.assertTrue(hasattr(integration.cron_sync, "__file__"))

class TestExecutorModules(unittest.TestCase):
    """执行器子模块测试"""

    def test_circuit_breaker(self):
        from executor.circuit_breaker import CircuitBreakerManager
        cb = CircuitBreakerManager()
        self.assertIsNotNone(cb)

    def test_response_cache(self):
        from executor.response_cache import ResponseCache
        cache = ResponseCache()
        self.assertIsNotNone(cache)

    def test_skill_loader(self):
        from executor.skill_loader import SkillLoader
        loader = SkillLoader("/tmp/nonexistent")
        self.assertIsNotNone(loader)

    def test_deep_compact(self):
        from executor.deep_compact import DeepCompactor
        dc = DeepCompactor()
        self.assertIsNotNone(dc)

    def test_micro_compact(self):
        from executor.micro_compact import MicroCompactor
        mc = MicroCompactor()
        self.assertIsNotNone(mc)

class TestRouterModules(unittest.TestCase):
    """路由子模块测试"""

    def test_intent_classifier(self):
        from router.intent_classifier import IntentClassifier
        ic = IntentClassifier()
        self.assertIsNotNone(ic)

    def test_query_complexity(self):
        import router.query_complexity
        self.assertTrue(hasattr(router.query_complexity, "__file__"))

    def test_gatekeeper(self):
        import router.gatekeeper
        self.assertTrue(hasattr(router.gatekeeper, "__file__"))

    def test_llm_classifier(self):
        from router.llm_classifier import LLMClassifier
        lc = LLMClassifier()
        self.assertIsNotNone(lc)

class TestMemoryModules(unittest.TestCase):
    """记忆子模块测试"""

    def test_auto_extract(self):
        import memory.auto_extract
        self.assertTrue(hasattr(memory.auto_extract, "__file__"))

    def test_memory_refiner(self):
        from memory.memory_refiner import MemoryRefiner
        mr = MemoryRefiner()
        self.assertIsNotNone(mr)

    def test_session_summary(self):
        import memory.diary
        self.assertTrue(hasattr(memory.diary, "__file__"))

class TestSecurityModules(unittest.TestCase):
    """安全子模块测试"""

    def test_token_tracker(self):
        from security.token_tracker import TokenTracker
        tt = TokenTracker()
        stats = tt.get_session_stats()
        self.assertIsInstance(stats, dict)

    def test_permission_system(self):
        from security.permission_system import PermissionSystem
        ps = PermissionSystem()
        self.assertIsNotNone(ps)

    def test_approval_system(self):
        from security.approval import ApprovalSystem
        ap = ApprovalSystem()
        self.assertIsNotNone(ap)

class TestSelfHealModules(unittest.TestCase):
    """自愈子模块测试"""

    def test_evolution(self):
        from self_heal.evolution import EvolutionEngine
        ee = EvolutionEngine()
        self.assertIsNotNone(ee)

    def test_skill_crystallizer(self):
        from self_heal.skill_crystallizer import SkillCrystallizer
        sc = SkillCrystallizer()
        self.assertIsNotNone(sc)

    def test_fault_playbook(self):
        from self_heal.fault_playbook import FaultPlaybook
        fp = FaultPlaybook()
        faults = fp.list_faults()
        self.assertIsInstance(faults, list)

if __name__ == "__main__":
    unittest.main(verbosity=2)
