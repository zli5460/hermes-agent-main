"""
不死鸟 Phoenix — 第十一板块：GitHub集成

自动提交、创建PR、代码审查、分支管理。

用法：
    from phoenix.github.client import GitHubClient
    
    gh = GitHubClient()
    
    # 提交代码
    gh.commit("修复了空指针问题", files=["main.py"])
    
    # 创建PR
    gh.create_pr("修复空指针", body="修复了main.py中的空指针问题")
    
    # 代码审查
    review = gh.review_pr(123)
"""

from .client import GitHubClient

__all__ = ["GitHubClient"]
