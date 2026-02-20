"""
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");

you may not use this file except in compliance with the License.

You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""


import importlib
import os
import sys
import unittest
from unittest.mock import patch

# pytest sometimes imports a different `services` module (e.g. an unrelated
# installed package) which lacks __path__. ensure our local package path is
# present so submodule imports work correctly.
try:
    import services
    if not hasattr(services, "__path__"):
        services.__path__ = [os.path.join(os.path.dirname(__file__), "..", "services")]
except ImportError:
    # if import fails, tests will likely fail later anyway
    pass


CONFIG_MODULE = "config"


def _reload_config_module():
    if CONFIG_MODULE in sys.modules:
        del sys.modules[CONFIG_MODULE]
    return importlib.import_module(CONFIG_MODULE)


class ConfigSecurityTests(unittest.TestCase):
    def test_rejects_example_database_url(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://beobservant:changeme123@localhost:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_rejects_wildcard_cors_with_credentials(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "*",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_generates_runtime_admin_password_when_missing(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "DEFAULT_ADMIN_PASSWORD": "",
            "JWT_PRIVATE_KEY": "",
            "JWT_PUBLIC_KEY": "",
        }, clear=False):
            module = _reload_config_module()
            self.assertTrue(module.config.DEFAULT_ADMIN_PASSWORD)
            self.assertNotEqual(module.config.DEFAULT_ADMIN_PASSWORD, "admin123")
            self.assertTrue(module.config.JWT_PRIVATE_KEY)
            self.assertTrue(module.config.JWT_PUBLIC_KEY)
            self.assertIn("BEGIN", module.config.JWT_PRIVATE_KEY)
            self.assertIn("BEGIN", module.config.JWT_PUBLIC_KEY)

    def test_rejects_non_asymmetric_jwt_algorithm(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "HS256",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_generates_es256_keypair_when_enabled(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "ES256",
            "JWT_PRIVATE_KEY": "",
            "JWT_PUBLIC_KEY": "",
            "JWT_AUTO_GENERATE_KEYS": "true",
            "APP_ENV": "development",
        }, clear=False):
            module = _reload_config_module()
            self.assertTrue(module.config.JWT_PRIVATE_KEY)
            self.assertTrue(module.config.JWT_PUBLIC_KEY)
            self.assertIn("BEGIN PRIVATE KEY", module.config.JWT_PRIVATE_KEY)
            self.assertIn("BEGIN PUBLIC KEY", module.config.JWT_PUBLIC_KEY)

    def test_rejects_bootstrap_and_auto_keys_in_production(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "CORS_ORIGINS": "https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "APP_ENV": "production",
            "DEFAULT_ADMIN_BOOTSTRAP_ENABLED": "true",
            "JWT_AUTO_GENERATE_KEYS": "true",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_vault_enabled_in_production_without_addr_raises(self):
        with patch.dict(os.environ, {
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "APP_ENV": "production",
            "VAULT_ENABLED": "true",
            # deliberately omit VAULT_ADDR
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
            "DEFAULT_ADMIN_PASSWORD": "strongProdPassword_123!",
        }, clear=False):
            with self.assertRaises(ValueError):
                _reload_config_module()

    def test_loads_secrets_from_vault_when_enabled(self):
        # Patch the VaultSecretProvider so tests don't require hvac or a real Vault
        class FakeVaultProvider:
            def __init__(self, *a, **k):
                pass

            def get(self, key):
                mapping = {
                    "DATABASE_URL": "postgresql://vaultuser:vaultpass@db:5432/beobservant",
                    "JWT_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----FAKE",
                    "JWT_PUBLIC_KEY": "-----BEGIN PUBLIC KEY-----FAKE",
                    "DEFAULT_ADMIN_PASSWORD": "vault-default-admin-pass",
                    "DATA_ENCRYPTION_KEY": "vault-data-key",
                }
                return mapping.get(key)

        with patch.dict(os.environ, {
            "CORS_ORIGINS": "http://localhost:5173",
            "CORS_ALLOW_CREDENTIALS": "true",
            "JWT_ALGORITHM": "RS256",
            "VAULT_ENABLED": "true",
            "VAULT_ADDR": "http://vault:8200",
            "DATABASE_URL": "postgresql://safeuser:safePass_123@db:5432/beobservant",
        }, clear=False):
            # insert a fake module into sys.modules so that when config.py
            # tries to import services.secrets.vault_client it sees our
            # provider class without touching the real package.  This avoids
            # odd AttributeError issues that were occurring during import.
            import types, sys
            fake = types.SimpleNamespace(VaultSecretProvider=FakeVaultProvider, VaultClientError=Exception)
            sys.modules['services.secrets.vault_client'] = fake
            try:
                module = _reload_config_module()
            finally:
                # clean up to avoid polluting other tests
                sys.modules.pop('services.secrets.vault_client', None)
                # values from fake provider override env
                self.assertEqual(module.config.DATABASE_URL, "postgresql://vaultuser:vaultpass@db:5432/beobservant")
                self.assertEqual(module.config.DEFAULT_ADMIN_PASSWORD, "vault-default-admin-pass")
                self.assertTrue(module.config.JWT_PRIVATE_KEY.startswith("-----BEGIN PRIVATE KEY"))
                self.assertTrue(module.config.JWT_PUBLIC_KEY.startswith("-----BEGIN PUBLIC KEY"))
                self.assertEqual(module.config.DATA_ENCRYPTION_KEY, "vault-data-key")


if __name__ == "__main__":
    unittest.main()
