from pydantic import BaseModel, Field, field_validator


class DeviceInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ip_address: str = Field(min_length=1, max_length=253)
    device_type: str = Field(pattern="^(ROUTER|SWITCH|SERVER|PC|ACCESS_POINT|OTHER)$")
    hostname: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "ip_address")
    @classmethod
    def strip_values(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be empty")
        return value


class MonitoringInput(BaseModel):
    monitoring_enabled: bool


class RegistrationInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)
