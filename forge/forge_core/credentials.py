from __future__ import annotations

import os
from typing import Final, Protocol

import keyring
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError, PasswordDeleteError

from .models import MODELS
from .providers import provider_credentials
from .redaction import register_secret

CREDENTIAL_SERVICE: Final = "forge-ai"
SECURE_SYSTEM_BACKEND_MODULES: Final = frozenset(
    {
        "keyring.backends.SecretService",
        "keyring.backends.Windows",
        "keyring.backends.kwallet",
        "keyring.backends.libsecret",
        "keyring.backends.macOS",
    }
)
SUPPORTED_CREDENTIALS: Final = (
    frozenset(model.requires_key for model in MODELS.values() if model.requires_key is not None)
    | provider_credentials()
)


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class SystemCredentialBackend:
    def get_password(self, service: str, username: str) -> str | None:
        return keyring.get_password(service, username)

    def set_password(self, service: str, username: str, password: str) -> None:
        keyring.set_password(service, username, password)

    def delete_password(self, service: str, username: str) -> None:
        keyring.delete_password(service, username)


class CredentialStoreError(Exception):
    pass


class CredentialStoreUnavailableError(CredentialStoreError):
    pass


class CredentialNameError(CredentialStoreError, ValueError):
    pass


class CredentialStore:
    def __init__(self, backend: CredentialBackend | None) -> None:
        self._backend = backend

    def get(self, name: str) -> str | None:
        _validate_name(name)
        if self._backend is None:
            return None
        try:
            value = self._backend.get_password(CREDENTIAL_SERVICE, name)
        except KeyringError as error:
            raise CredentialStoreUnavailableError(
                "The operating-system secure credential store is unavailable."
            ) from error
        return _normalize(value)

    def set(self, name: str, value: str) -> None:
        _validate_name(name)
        secret = _normalize(value)
        if secret is None:
            raise CredentialStoreError("Provider credential must not be blank.")
        if self._backend is None:
            raise CredentialStoreUnavailableError(
                "The operating-system secure credential store is unavailable."
            )
        try:
            self._backend.set_password(CREDENTIAL_SERVICE, name, secret)
        except KeyringError as error:
            raise CredentialStoreUnavailableError(
                "The operating-system secure credential store is unavailable."
            ) from error
        register_secret(secret)

    def delete(self, name: str) -> None:
        _validate_name(name)
        if self._backend is None:
            raise CredentialStoreUnavailableError(
                "The operating-system secure credential store is unavailable."
            )
        try:
            self._backend.delete_password(CREDENTIAL_SERVICE, name)
        except PasswordDeleteError:
            return
        except KeyringError as error:
            raise CredentialStoreUnavailableError(
                "The operating-system secure credential store is unavailable."
            ) from error


def system_credential_store() -> CredentialStore:
    backend = keyring.get_keyring()
    if not _is_secure_system_backend(backend):
        return CredentialStore(None)
    return CredentialStore(SystemCredentialBackend())


def resolve_credential(name: str | None, store: CredentialStore | None = None) -> str | None:
    if name is None:
        return None
    environment_value = _normalize(os.getenv(name))
    if environment_value is not None:
        register_secret(environment_value)
        return environment_value
    if name not in SUPPORTED_CREDENTIALS:
        return None
    credential_store = store or system_credential_store()
    try:
        value = credential_store.get(name)
    except CredentialStoreUnavailableError:
        return None
    if value is not None:
        register_secret(value)
    return value


def _validate_name(name: str) -> None:
    if name not in SUPPORTED_CREDENTIALS:
        raise CredentialNameError(f"Unsupported provider credential: {name}")


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _is_secure_system_backend(backend: KeyringBackend) -> bool:
    return type(backend).__module__ in SECURE_SYSTEM_BACKEND_MODULES
