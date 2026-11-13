import sys


class KeychainVault:
    """Use the native macOS Keychain through keyring's macOS backend only."""
    service = "app.pawilot.credentials"

    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("PAWilot credentials require macOS Keychain")
        from keyring.backends.macOS import Keyring
        self.backend = Keyring()

    def get(self, name):
        return self.backend.get_password(self.service, name)

    def set(self, name, value):
        self.backend.set_password(self.service, name, value)

    def delete(self, name):
        if self.get(name) is not None:
            self.backend.delete_password(self.service, name)


class MemoryVault:
    """Explicit test-only credential store; never used by the app launcher."""
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)

