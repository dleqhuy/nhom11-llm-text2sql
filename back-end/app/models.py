from pydantic import BaseModel, Field, field_validator


class Prompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)

    @field_validator("prompt")
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Prompt không được để trống.")
        return value


class CreateThread(Prompt):
    name: str | None = Field(default=None, min_length=1, max_length=100)
