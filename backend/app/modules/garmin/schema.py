from pydantic import BaseModel


class GarminLogin(BaseModel):
    username: str
    password: str
    is_cn: bool = False


class MFARequest(BaseModel):
    mfa_code: str
