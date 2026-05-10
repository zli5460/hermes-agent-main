"""
Phoenix GitHub客户端

通过gh CLI操作GitHub：提交、PR、审查、分支管理。
"""

import os
import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass

logger = logging.getLogger("phoenix.github")


@dataclass
class PRInfo:
    """PR信息"""
    number: int
    title: str
    state: str
    url: str
    author: str
    created_at: str
    body: str = ""


class GitHubClient:
    """
    GitHub客户端
    
    通过gh CLI操作GitHub。
    
    用法：
        gh = GitHubClient()
        
        # 检查是否可用
        if gh.is_available():
            # 提交代码
            gh.commit("修复bug", files=["main.py"])
            
            # 创建PR
            pr = gh.create_pr("新功能", body="实现了xxx")
            
            # 获取PR列表
            prs = gh.list_prs(state="open")
    """
    
    def __init__(self, repo_path: Optional[str] = None):
        self._repo_path = repo_path or os.getcwd()
        self._gh_bin = self._find_gh()
    
    def _find_gh(self) -> str:
        """找到gh CLI"""
        try:
            result = subprocess.run(
                ["which", "gh"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as exc:
            _ = exc
        return ""
    
    def _run(self, args: List[str], timeout: int = 30) -> dict:
        """执行gh命令"""
        if not self._gh_bin:
            return {"success": False, "error": "gh CLI未安装"}
        
        try:
            result = subprocess.run(
                [self._gh_bin] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self._repo_path
            )
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout.strip(),
                "error": result.stderr.strip(),
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "命令超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def is_available(self) -> bool:
        """检查gh是否可用"""
        return bool(self._gh_bin)
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
        result = self._run(["auth", "status"])
        return result["success"]
    
    def get_repo(self) -> Optional[str]:
        """获取当前仓库"""
        result = self._run(["repo", "view", "--json", "nameWithOwner"])
        if result["success"]:
            try:
                data = json.loads(result["output"])
                return data.get("nameWithOwner")
            except Exception as exc:
                _ = exc
        return None
    
    # === 分支操作 ===
    
    def create_branch(self, name: str) -> bool:
        """创建并切换到新分支"""
        # 先确保在最新代码
        self._run(["pull", "--rebase"])
        
        # 创建分支
        result = self._run(["checkout", "-b", name])
        return result["success"]
    
    def current_branch(self) -> str:
        """获取当前分支名"""
        result = self._run(["branch", "--show-current"])
        return result["output"] if result["success"] else ""
    
    # === 提交操作 ===
    
    def stage_files(self, files: List[str]) -> bool:
        """暂存文件"""
        result = self._run(["add"] + files)
        return result["success"]
    
    def commit(self, message: str, files: List[str] = None) -> bool:
        """
        提交代码
        
        Args:
            message: 提交信息
            files: 要提交的文件列表（None则提交所有暂存文件）
        """
        if files:
            self.stage_files(files)
        
        result = self._run(["commit", "-m", message])
        if result["success"]:
            logger.info("Committed: %s", message)
        return result["success"]
    
    def push(self, branch: str = None) -> bool:
        """推送到远程"""
        if not branch:
            branch = self.current_branch()
        result = self._run(["push", "origin", branch])
        return result["success"]
    
    # === PR操作 ===
    
    def create_pr(self, title: str, body: str = "", 
                  base: str = "main", draft: bool = False) -> Optional[PRInfo]:
        """
        创建PR
        
        Args:
            title: PR标题
            body: PR描述
            base: 目标分支
            draft: 是否为草稿
        """
        args = ["pr", "create", "--title", title, "--base", base]
        if body:
            args.extend(["--body", body])
        if draft:
            args.append("--draft")
        
        result = self._run(args)
        if result["success"]:
            # 解析PR URL
            url = result["output"]
            number = int(url.split("/")[-1]) if "/" in url else 0
            
            pr = PRInfo(
                number=number,
                title=title,
                state="open",
                url=url,
                author="",
                created_at="",
                body=body,
            )
            logger.info("PR created: #%d %s", number, title)
            return pr
        return None
    
    def list_prs(self, state: str = "open", limit: int = 10) -> List[PRInfo]:
        """列出PR"""
        args = [
            "pr", "list", "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,url,author,createdAt,body"
        ]
        
        result = self._run(args)
        if not result["success"]:
            return []
        
        try:
            prs_data = json.loads(result["output"])
            return [
                PRInfo(
                    number=pr["number"],
                    title=pr["title"],
                    state=pr["state"],
                    url=pr["url"],
                    author=pr.get("author", {}).get("login", ""),
                    created_at=pr.get("createdAt", ""),
                    body=pr.get("body", ""),
                )
                for pr in prs_data
            ]
        except Exception:
            return []
    
    def get_pr(self, number: int) -> Optional[PRInfo]:
        """获取PR详情"""
        args = [
            "pr", "view", str(number),
            "--json", "number,title,state,url,author,createdAt,body"
        ]
        
        result = self._run(args)
        if not result["success"]:
            return None
        
        try:
            pr = json.loads(result["output"])
            return PRInfo(
                number=pr["number"],
                title=pr["title"],
                state=pr["state"],
                url=pr["url"],
                author=pr.get("author", {}).get("login", ""),
                created_at=pr.get("createdAt", ""),
                body=pr.get("body", ""),
            )
        except Exception:
            return None
    
    def merge_pr(self, number: int, method: str = "squash") -> bool:
        """合并PR"""
        result = self._run(["pr", "merge", str(number), "--" + method])
        return result["success"]
    
    def close_pr(self, number: int) -> bool:
        """关闭PR"""
        result = self._run(["pr", "close", str(number)])
        return result["success"]
    
    # === 审查操作 ===
    
    def review_pr(self, number: int) -> Optional[dict]:
        """获取PR审查信息"""
        args = [
            "pr", "view", str(number),
            "--json", "reviews,comments"
        ]
        
        result = self._run(args)
        if not result["success"]:
            return None
        
        try:
            return json.loads(result["output"])
        except Exception:
            return None
    
    # === Issue操作 ===
    
    def create_issue(self, title: str, body: str = "", 
                     labels: List[str] = None) -> Optional[int]:
        """创建Issue"""
        args = ["issue", "create", "--title", title]
        if body:
            args.extend(["--body", body])
        if labels:
            args.extend(["--label", ",".join(labels)])
        
        result = self._run(args)
        if result["success"]:
            # 从输出中提取Issue编号
            try:
                number = int(result["output"].split("/")[-1])
                return number
            except Exception as exc:
                _ = exc
        return None
    
    def list_issues(self, state: str = "open", limit: int = 10) -> List[dict]:
        """列出Issue"""
        args = [
            "issue", "list", "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,url,labels"
        ]
        
        result = self._run(args)
        if not result["success"]:
            return []
        
        try:
            return json.loads(result["output"])
        except Exception:
            return []
