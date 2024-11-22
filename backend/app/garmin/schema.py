from pydantic import BaseModel


class GarminLogin(BaseModel):
    username: str
    password: str


class MFARequest(BaseModel):
    mfa_code: str


class MFACodeStore:
    def __init__(self):
        self._store = {}

    def add_code(self, user_id, code):
        self._store[user_id] = code

    def get_code(self, user_id):
        return self._store.get(user_id)

    def delete_code(self, user_id):
        if user_id in self._store:
            del self._store[user_id]

    def has_code(self, user_id):
        return user_id in self._store

    def clear_all(self):
        self._store.clear()

    def __repr__(self):
        return f"{self._store}"


def get_mfa_store():
    return mfa_store


mfa_store = MFACodeStore()
