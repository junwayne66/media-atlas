"""本地凭据库的纯单元测试：不使用真实 Secret 或外部网络。"""

from dataclasses import replace

import pytest

from videoforge_api.credential_vault import (
    CredentialVault,
    InvalidPassphraseError,
    VaultBusyError,
    VaultLockedError,
)

PASSPHRASE = "synthetic-correct-horse-2026"
SECRET = b'{"api_key":"VF_SECRET_CANARY_UNIT"}'


def test_envelope_unlock_lock_and_restart_state() -> None:
    vault = CredentialVault()
    envelope, master_key = vault.create_envelope(PASSPHRASE)
    assert vault.is_unlocked is False

    vault.activate(master_key)
    assert vault.is_unlocked is True
    vault.lock()
    assert vault.is_unlocked is False

    restarted = CredentialVault()
    assert restarted.is_unlocked is False
    restarted.unlock(PASSPHRASE, envelope)
    assert restarted.is_unlocked is True


def test_wrong_passphrase_and_wrapped_key_tamper_are_generic_failures() -> None:
    vault = CredentialVault()
    envelope, master_key = vault.create_envelope(PASSPHRASE)
    vault.wipe(master_key)

    with pytest.raises(InvalidPassphraseError, match="无法解锁"):
        vault.unlock("wrong-synthetic-passphrase", envelope)

    corrupted = replace(
        envelope,
        wrapped_key_tag=envelope.wrapped_key_tag[:-1]
        + bytes([envelope.wrapped_key_tag[-1] ^ 0x01]),
    )
    with pytest.raises(InvalidPassphraseError, match="无法解锁"):
        vault.unlock(PASSPHRASE, corrupted)


def test_aead_uses_fresh_nonce_and_authenticates_aad_and_ciphertext() -> None:
    vault = CredentialVault()
    envelope, master_key = vault.create_envelope(PASSPHRASE)
    vault.activate(master_key)
    aad = b"videoforge:credential:v1:entry:PROVIDER:LLM:api"

    with vault.lease() as key:
        first = vault.encrypt(key, SECRET, aad=aad)
        second = vault.encrypt(key, SECRET, aad=aad)
        assert first.nonce != second.nonce
        assert first.ciphertext != second.ciphertext
        assert vault.decrypt(key, first, aad=aad) == SECRET

        with pytest.raises(InvalidPassphraseError):
            vault.decrypt(key, first, aad=b"wrong-owner")

        tampered = replace(
            first,
            ciphertext=first.ciphertext[:-1] + bytes([first.ciphertext[-1] ^ 0x01]),
        )
        with pytest.raises(InvalidPassphraseError):
            vault.decrypt(key, tampered, aad=aad)


def test_locked_vault_refuses_key_lease() -> None:
    vault = CredentialVault()
    with pytest.raises(VaultLockedError, match="已锁定"):
        with vault.lease():
            raise AssertionError("unreachable")


def test_failed_unlocks_are_rate_limited_in_process() -> None:
    vault = CredentialVault()
    envelope, master_key = vault.create_envelope(PASSPHRASE)
    vault.wipe(master_key)
    for index in range(5):
        with pytest.raises(InvalidPassphraseError):
            vault.unlock(f"wrong-passphrase-{index}", envelope)
    with pytest.raises(VaultBusyError, match="稍后"):
        vault.unlock("one-more-wrong-passphrase", envelope)
