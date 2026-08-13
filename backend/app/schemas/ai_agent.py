from pydantic import BaseModel, ConfigDict, Field


class AIAgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1)


class AIAgentChatResponse(BaseModel):
    answer: str
    tools_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_quality_notes: list[str] = Field(default_factory=list)
