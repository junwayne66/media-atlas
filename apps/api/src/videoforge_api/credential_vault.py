"""进程内本地凭据库：Argon2id KEK + AES-256-GCM envelope encryption。

安全边界：
- 数据库只保存 wrapped master key 与认证密文；
- passphrase、KEK、明文 master key 不落盘；
- API 进程启动时总是锁定；
- `lease()` 持有 RLock，调用方可把整个数据库事务放在 lease 内，使 lock/save 线性化。

Python 与 C 扩展可能产生不可控的临时副本，因此内存覆零是 best-effort，不声称能抵御进程内存
转储；本模块主要保护本地数据库卷和备份的静态泄露。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import BoundedSemaphore, RLock
from time import monotonic
from typing import Any

from argon2.low_level import ARGON2_VERSION, Type, hash_secret_raw
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

CRYPTO_VERSION = 1
MASTER_KEY_BYTES = 32
NONCE_BYTES = 16
TAG_BYTES = 16
MAX_FAILED_UNLOCKS = 5
FAILED_UNLOCK_WINDOW_SECONDS = 60.0
_WRAP_AAD = b"videoforge:vault:wrapped-master-key:v1"
_DEFAULT_KDF: dict[str, Any] = {
    "type": "ID",
    "version": ARGON2_VERSION,
    "time_cost": 3,
    "memory_cost": 65536,
    "parallelism": 4,
    "hash_length": 32,
}


class VaultError(Exception):
    """凭据库稳定错误基类；异常文本不得包含调用方输入。"""


class VaultLockedError(VaultError):
    pass


class VaultBusyError(VaultError):
    pass


class InvalidPassphraseError(VaultError):
    pass


@dataclass(frozen=True)
class VaultEnvelope:
    crypto_version: int
    kdf_name: str
    kdf_parameters: dict[str, Any]
    salt: bytes
    wrapped_key_nonce: bytes
    wrapped_master_key: bytes
    wrapped_key_tag: bytes


@dataclass(frozen=True)
class EncryptedPayload:
    nonce: bytes
    ciphertext: bytes
    auth_tag: bytes


class CredentialVault:
    """单 API 进程的一份解锁态。不要按请求创建。"""

    def __init__(self) -> None:
        self._key_lock = RLock()
        self._kdf_capacity = BoundedSemaphore(1)
        self._master_key: bytearray | None = None
        self._failed_unlocks: deque[float] = deque()

    @property
    def is_unlocked(self) -> bool:
        with self._key_lock:
            return self._master_key is not None

    @staticmethod
    def wipe(value: bytearray | None) -> None:
        if value is None:
            return
        for index in range(len(value)):
            value[index] = 0

    def create_envelope(self, passphrase: str) -> tuple[VaultEnvelope, bytearray]:
        """生成 wrapped master key，但不改变当前解锁态。

        调用方必须先持久化 envelope 并提交事务，再调用 `activate(master_key)`；失败时调用
        `wipe(master_key)`。这样数据库初始化失败不会留下“内存已解锁、落库未成功”的假状态。
        """

        salt = get_random_bytes(16)
        master_key = bytearray(get_random_bytes(MASTER_KEY_BYTES))
        kek = self._derive_key(passphrase, salt, _DEFAULT_KDF)
        try:
            cipher = AES.new(
                kek,
                AES.MODE_GCM,
                nonce=get_random_bytes(NONCE_BYTES),
                mac_len=TAG_BYTES,
            )
            cipher.update(_WRAP_AAD)
            wrapped, tag = cipher.encrypt_and_digest(master_key)
            envelope = VaultEnvelope(
                crypto_version=CRYPTO_VERSION,
                kdf_name="argon2id",
                kdf_parameters=dict(_DEFAULT_KDF),
                salt=salt,
                wrapped_key_nonce=bytes(cipher.nonce),
                wrapped_master_key=wrapped,
                wrapped_key_tag=tag,
            )
            return envelope, master_key
        except BaseException:
            self.wipe(master_key)
            raise
        finally:
            self.wipe(kek)

    def unlock(self, passphrase: str, envelope: VaultEnvelope) -> None:
        self._check_unlock_rate()
        self._validate_envelope(envelope)
        kek = self._derive_key(passphrase, envelope.salt, envelope.kdf_parameters)
        candidate: bytearray | None = None
        try:
            cipher = AES.new(
                kek,
                AES.MODE_GCM,
                nonce=envelope.wrapped_key_nonce,
                mac_len=TAG_BYTES,
            )
            cipher.update(_WRAP_AAD)
            try:
                raw = cipher.decrypt_and_verify(
                    envelope.wrapped_master_key,
                    envelope.wrapped_key_tag,
                )
            except ValueError as exc:
                self._record_failed_unlock()
                raise InvalidPassphraseError(
                    "无法解锁凭据库：口令错误或本地凭据库已损坏"
                ) from exc
            if len(raw) != MASTER_KEY_BYTES:
                raise InvalidPassphraseError("无法解锁凭据库：本地凭据库材料无效")
            candidate = bytearray(raw)
            self.activate(candidate)
            candidate = None  # activate 已覆零调用方 buffer
            with self._key_lock:
                self._failed_unlocks.clear()
        finally:
            self.wipe(kek)
            self.wipe(candidate)

    def activate(self, master_key: bytearray) -> None:
        if len(master_key) != MASTER_KEY_BYTES:
            self.wipe(master_key)
            raise ValueError("master key 长度无效")
        with self._key_lock:
            self.wipe(self._master_key)
            self._master_key = bytearray(master_key)
            self.wipe(master_key)

    def lock(self) -> None:
        with self._key_lock:
            self.wipe(self._master_key)
            self._master_key = None

    @contextmanager
    def lease(self) -> Iterator[bytearray]:
        """持锁借用 master key；调用方应把整个 Secret 数据库事务放在此上下文内。"""

        with self._key_lock:
            if self._master_key is None:
                raise VaultLockedError("本地凭据库已锁定")
            yield self._master_key

    def encrypt(self, key: bytearray, plaintext: bytes, *, aad: bytes) -> EncryptedPayload:
        if len(key) != MASTER_KEY_BYTES:
            raise VaultLockedError("本地凭据库已锁定")
        cipher = AES.new(
            key,
            AES.MODE_GCM,
            nonce=get_random_bytes(NONCE_BYTES),
            mac_len=TAG_BYTES,
        )
        cipher.update(aad)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return EncryptedPayload(nonce=bytes(cipher.nonce), ciphertext=ciphertext, auth_tag=tag)

    def decrypt(
        self,
        key: bytearray,
        payload: EncryptedPayload,
        *,
        aad: bytes,
    ) -> bytes:
        if len(key) != MASTER_KEY_BYTES:
            raise VaultLockedError("本地凭据库已锁定")
        cipher = AES.new(key, AES.MODE_GCM, nonce=payload.nonce, mac_len=TAG_BYTES)
        cipher.update(aad)
        try:
            return cipher.decrypt_and_verify(payload.ciphertext, payload.auth_tag)
        except ValueError as exc:
            raise InvalidPassphraseError("凭据认证失败：口令错误或密文已损坏") from exc

    def _derive_key(
        self,
        passphrase: str,
        salt: bytes,
        parameters: dict[str, Any],
    ) -> bytearray:
        if not self._kdf_capacity.acquire(blocking=False):
            raise VaultBusyError("凭据库正在处理另一次口令操作，请稍后重试")
        passphrase_buffer = bytearray(passphrase.encode("utf-8"))
        try:
            raw = hash_secret_raw(
                secret=bytes(passphrase_buffer),
                salt=salt,
                time_cost=int(parameters["time_cost"]),
                memory_cost=int(parameters["memory_cost"]),
                parallelism=int(parameters["parallelism"]),
                hash_len=int(parameters["hash_length"]),
                type=Type.ID,
                version=int(parameters["version"]),
            )
            return bytearray(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidPassphraseError("无法解锁凭据库：KDF 参数无效") from exc
        finally:
            self.wipe(passphrase_buffer)
            self._kdf_capacity.release()

    @staticmethod
    def _validate_envelope(envelope: VaultEnvelope) -> None:
        params = envelope.kdf_parameters
        valid = (
            envelope.crypto_version == CRYPTO_VERSION
            and envelope.kdf_name == "argon2id"
            and 16 <= len(envelope.salt) <= 64
            and len(envelope.wrapped_key_nonce) == NONCE_BYTES
            and len(envelope.wrapped_master_key) == MASTER_KEY_BYTES
            and len(envelope.wrapped_key_tag) == TAG_BYTES
            and params.get("type") == "ID"
            and params.get("version") == ARGON2_VERSION
            and 1 <= int(params.get("time_cost", 0)) <= 10
            and 8192 <= int(params.get("memory_cost", 0)) <= 262144
            and 1 <= int(params.get("parallelism", 0)) <= 8
            and int(params.get("hash_length", 0)) == MASTER_KEY_BYTES
        )
        if not valid:
            raise InvalidPassphraseError("无法解锁凭据库：本地凭据库材料无效")

    def _check_unlock_rate(self) -> None:
        with self._key_lock:
            now = monotonic()
            while (
                self._failed_unlocks
                and now - self._failed_unlocks[0] > FAILED_UNLOCK_WINDOW_SECONDS
            ):
                self._failed_unlocks.popleft()
            if len(self._failed_unlocks) >= MAX_FAILED_UNLOCKS:
                raise VaultBusyError("解锁失败次数过多，请稍后重试")

    def _record_failed_unlock(self) -> None:
        with self._key_lock:
            self._failed_unlocks.append(monotonic())


__all__ = [
    "CredentialVault",
    "EncryptedPayload",
    "InvalidPassphraseError",
    "VaultBusyError",
    "VaultEnvelope",
    "VaultError",
    "VaultLockedError",
]
