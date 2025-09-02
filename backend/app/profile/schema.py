from pydantic import BaseModel


class MFARequest(BaseModel):
    mfa_code: str


class MFASetupRequest(BaseModel):
    mfa_code: str


class MFASetupResponse(BaseModel):
    secret: str
    qr_code: str
    app_name: str = "Endurain"


class MFADisableRequest(BaseModel):
    mfa_code: str


class MFAStatusResponse(BaseModel):
    mfa_enabled: bool


class MFASecretStore:
    """Temporary storage for MFA secrets during setup process"""

    def __init__(self):
        self._store = {}

    def add_secret(self, user_id: int, secret: str):
        self._store[user_id] = secret

    def get_secret(self, user_id: int):
        return self._store.get(user_id)

    def delete_secret(self, user_id: int):
        if user_id in self._store:
            del self._store[user_id]

    def has_secret(self, user_id: int):
        return user_id in self._store

    def clear_all(self):
        self._store.clear()

    def __repr__(self):
        return f"{self._store}"


def get_mfa_secret_store():
    return mfa_secret_store


mfa_secret_store = MFASecretStore()
