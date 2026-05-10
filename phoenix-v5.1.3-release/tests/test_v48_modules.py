"""Phoenix V5.1 新模块单元测试"""
import unittest
import sys
import os

sys.path.insert(0, os.path.expanduser("~/.hermes"))
sys.path.insert(0, ".")


class TestCreditMonitor(unittest.TestCase):
    """信用监控测试"""
    
    def test_import(self):
        from core.credit_monitor import CreditMonitor, CreditStatus
        self.assertTrue(True)
    
    def test_status_creation(self):
        from core.credit_monitor import CreditStatus
        s = CreditStatus(provider="test", is_exhausted=False, last_check=0)
        self.assertFalse(s.is_exhausted)
    
    def test_should_fallback(self):
        from core.credit_monitor import CreditMonitor
        config = {
            "credit_monitor": {"enabled": True, "auto_fallback_to_primary": True},
            "router": {"primary_model": {"model": "test", "api_key": "key", "base_url": "url"}}
        }
        m = CreditMonitor(config)
        self.assertFalse(m.should_fallback())


class TestSkillReviewer(unittest.TestCase):
    """技能审稿测试"""
    
    def test_import(self):
        from core.skill_reviewer import SkillReviewer
        self.assertTrue(True)
    
    def test_reviewer_init(self):
        from core.skill_reviewer import SkillReviewer
        r = SkillReviewer()
        self.assertIsNotNone(r)


class TestParallelExecutor(unittest.TestCase):
    """并行执行测试"""
    
    def test_import(self):
        from executor.parallel_executor import ParallelSubAgentExecutor
        self.assertTrue(True)
    
    def test_executor_init(self):
        from executor.parallel_executor import ParallelSubAgentExecutor
        e = ParallelSubAgentExecutor(max_workers=2)
        self.assertEqual(e.max_workers, 2)


class TestProgressiveLoader(unittest.TestCase):
    """渐进式加载测试"""
    
    def test_import(self):
        from executor.progressive_loader import ProgressiveSkillLoader
        self.assertTrue(True)
    
    def test_loader_init(self):
        from executor.progressive_loader import ProgressiveSkillLoader
        l = ProgressiveSkillLoader("/tmp/test_skills")
        self.assertIsNotNone(l)


class TestDeferredToolLoader(unittest.TestCase):
    """延迟工具加载测试"""
    
    def test_import(self):
        from executor.deferred_tool_loader import DeferredToolLoader
        self.assertTrue(True)
    
    def test_loader_init(self):
        from executor.deferred_tool_loader import DeferredToolLoader
        l = DeferredToolLoader()
        self.assertIsNotNone(l)
    
    def test_search_empty(self):
        from executor.deferred_tool_loader import DeferredToolLoader
        l = DeferredToolLoader()
        results = l.search_tools("test")
        self.assertEqual(len(results), 0)


class TestStructuredMemory(unittest.TestCase):
    """结构化记忆测试"""
    
    def test_import(self):
        from memory.structured_memory import StructuredMemory
        self.assertTrue(True)
    
    def test_memory_init(self):
        from memory.structured_memory import StructuredMemory
        import tempfile
        m = StructuredMemory(tempfile.mkdtemp())
        self.assertIsNotNone(m)
    
    def test_add_fact(self):
        from memory.structured_memory import StructuredMemory
        import tempfile
        m = StructuredMemory(tempfile.mkdtemp())
        fact = m.add_fact("test fact", "context", 0.8)
        self.assertEqual(fact.content, "test fact")
        self.assertEqual(fact.confidence, 0.8)


class TestGuardrailMiddleware(unittest.TestCase):
    """护栏中间件测试"""
    
    def test_import(self):
        from security.guardrail_middleware import GuardrailMiddleware
        self.assertTrue(True)
    
    def test_middleware_init(self):
        from security.guardrail_middleware import GuardrailMiddleware
        m = GuardrailMiddleware()
        self.assertIsNotNone(m)
    
    def test_check_pass(self):
        from security.guardrail_middleware import GuardrailMiddleware
        m = GuardrailMiddleware()
        result = m.check({"message": "hello"})
        self.assertTrue(result.passed)
    
    def test_check_dangerous(self):
        from security.guardrail_middleware import GuardrailMiddleware, check_no_dangerous_commands
        m = GuardrailMiddleware()
        m.register("dangerous", check_no_dangerous_commands, "block")
        result = m.check({"message": "rm -rf /"})
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
