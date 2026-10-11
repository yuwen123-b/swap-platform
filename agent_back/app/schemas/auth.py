from pydantic import BaseModel, EmailStr, Field


class SendCodeRequest(BaseModel):
    target: str = Field(min_length=3, max_length=50)
    target_type: str
    scene: str


class RegisterRequest(BaseModel):
    register_type: str
    phone: str | None = Field(default=None, min_length=11, max_length=11)
    email: EmailStr | None = None
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(min_length=1, max_length=50)
    code: str = Field(min_length=6, max_length=6)


class EmailCodeLoginRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class PhoneCodeLoginRequest(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)


class PasswordLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=64)
