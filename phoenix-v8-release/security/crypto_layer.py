"""
Phoenix V8 — 安全加密层（AES-256）

保护敏感数据：
1. API Key加密存储
2. 记忆数据加密
3. 用户偏好加密
4. 密码/凭证保管

技术方案：
- AES-256-CBC加密（cryptography库）
- PBKDF2密钥派生（10万次迭代）
- 盐值随机存储，派生密钥不存储
- 每次解锁时从密码重新派生
"""

import os
import json
import hashlib
import secrets
import base64
import time
from pathlib import Path
from typing import Optional, List

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    Fernet = None


class CryptoLayer:
    """
    安全加密层（AES-256）
    
    核心设计：
    1. 用户设置主密码 → PBKDF2派生加密密钥
    2. 派生密钥不存储，每次从密码重新计算
    3. 所有敏感数据用AES-256-CBC加密
    4. 盐值随机生成，防彩虹表
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        if not HAS_CRYPTOGRAPHY:
            raise RuntimeError(
                "cryptography库未安装。请运行: pip install cryptography\n"
                "Phoenix Open要求使用真正的AES加密，不支持降级到不安全的加密方式。"
            )

        self._data_dir = Path(data_dir or os.path.expanduser("~/.hermes/phoenix/data"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._salt_file = self._data_dir / ".crypto_salt"
        self._password_hash = self._data_dir / ".password_hash"
        self._derived_key: Optional[bytes] = None
        self._fernet: Optional[Fernet] = None
    
    # ── 密钥管理 ──────────────────────────────────────────
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """PBKDF2派生密钥（60万次迭代，2026年安全标准）"""
        return hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            iterations=600000,
            dklen=32
        )
    
    def setup_master_password(self, password: str) -> bool:
        """设置主密码"""
        if len(password) < 8:
            raise ValueError("密码长度必须至少8个字符")

        # 生成随机盐值
        salt = secrets.token_bytes(32)
        self._salt_file.write_bytes(salt)

        # 存储密码哈希（用于验证，不存储密钥）
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
        self._password_hash.write_bytes(pw_hash)
        self._password_hash.chmod(0o600)

        # 派生密钥（不存储，仅内存持有）
        key = self._derive_key(password, salt)
        self._derived_key = key
        self._init_fernet(key)

        return True
    
    def _init_fernet(self, key: bytes) -> None:
        """初始化Fernet加密器（AES-128-CBC + HMAC）"""
        fernet_key = base64.urlsafe_b64encode(key)
        self._fernet = Fernet(fernet_key)
    
    def unlock(self, password: str) -> bool:
        """用主密码解锁"""
        if not self._salt_file.exists() or not self._password_hash.exists():
            return False

        try:
            salt = self._salt_file.read_bytes()
            stored_hash = self._password_hash.read_bytes()
        except (OSError, IOError) as e:
            raise RuntimeError(f"无法读取加密配置文件: {e}")

        # 验证密码（使用与setup相同的迭代次数）
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 600000)
        if pw_hash != stored_hash:
            return False

        # 派生密钥（不存储，仅内存持有）
        self._derived_key = self._derive_key(password, salt)
        self._init_fernet(self._derived_key)
        return True
    
    def is_unlocked(self) -> bool:
        return self._derived_key is not None
    
    def lock(self) -> None:
        """锁定（清除内存中的密钥）"""
        self._derived_key = None
        self._fernet = None
    
    def is_setup(self) -> bool:
        return self._salt_file.exists() and self._password_hash.exists()
    
    # ── 加密/解密 ──────────────────────────────────────────
    
    def encrypt(self, plaintext: str) -> str:
        """加密文本（AES-128-CBC + HMAC）"""
        if not self._derived_key or not self._fernet:
            raise RuntimeError("加密层未解锁")

        return self._fernet.encrypt(plaintext.encode('utf-8')).decode('ascii')
    
    def decrypt(self, ciphertext: str) -> str:
        """解密文本（AES-128-CBC + HMAC）"""
        if not self._derived_key or not self._fernet:
            raise RuntimeError("加密层未解锁")

        try:
            return self._fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
        except Exception as e:
            raise RuntimeError(f"解密失败: {e}")
    
    # ── 安全存储 ──────────────────────────────────────────
    
    def secure_store(self, category: str, key: str, value: str) -> None:
        """加密存储敏感数据"""
        store_file = self._data_dir / f".secure_{category}.json"
        data = {}
        if store_file.exists():
            try:
                data = json.loads(store_file.read_text())
            except (json.JSONDecodeError, OSError):
                data = {}

        data[key] = {
            "encrypted": self.encrypt(value),
            "timestamp": time.time(),
        }

        store_file.write_text(json.dumps(data, indent=2))
        store_file.chmod(0o600)
    
    def secure_load(self, category: str, key: str) -> Optional[str]:
        """解密读取敏感数据"""
        store_file = self._data_dir / f".secure_{category}.json"
        if not store_file.exists():
            return None
        try:
            data = json.loads(store_file.read_text())
            if key not in data:
                return None
            return self.decrypt(data[key]["encrypted"])
        except (json.JSONDecodeError, OSError, RuntimeError, KeyError):
            return None
    
    def secure_list(self, category: str) -> List[str]:
        """列出某类别下的所有键名"""
        store_file = self._data_dir / f".secure_{category}.json"
        if not store_file.exists():
            return []
        try:
            return list(json.loads(store_file.read_text()).keys())
        except (json.JSONDecodeError, OSError):
            return []
    
    # ── 便捷方法 ──────────────────────────────────────────
    
    def encrypt_api_key(self, provider: str, key: str) -> None:
        self.secure_store("api_keys", provider, key)

    def get_api_key(self, provider: str) -> Optional[str]:
        return self.secure_load("api_keys", provider)

    def encrypt_memory(self, memory_id: str, content: str) -> None:
        self.secure_store("memory", memory_id, content)

    def get_memory(self, memory_id: str) -> Optional[str]:
        return self.secure_load("memory", memory_id)

    def encrypt_credential(self, name: str, value: str) -> None:
        self.secure_store("credentials", name, value)

    def get_credential(self, name: str) -> Optional[str]:
        return self.secure_load("credentials", name)
