import re
from pydantic import BaseModel, Field, EmailStr, field_validator


class UserAuthSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    email: EmailStr
    password: str
    role: str = "USER"

    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                'Username must contain only letters, numbers, and underscores.')
        return v

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, value: str) -> str:
        missing_requirements = []
        if len(value) < 8:
            missing_requirements.append("at least 8 characters")
        if not re.search(r"[A-Z]", value):
            missing_requirements.append("at least one uppercase letter")
        if not re.search(r"\d", value):
            missing_requirements.append("at least one number")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", value):
            missing_requirements.append("at least one special character")

        if missing_requirements:
            joined_errors = ", ".join(missing_requirements)
            raise ValueError(f"Password must contain {joined_errors}.")
        return value


class HardwareSchema(BaseModel):
    item_name: str = Field(..., min_length=2, max_length=100)
    category: str = Field(..., min_length=2, max_length=50)
    quantity: int = Field(..., ge=0)
    unit_price: float = Field(..., gt=0)
