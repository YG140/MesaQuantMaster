class AIAgentError(Exception):
    """Erro controlado e seguro do agente."""


class AIProviderUnavailableError(AIAgentError):
    pass


class AILimitExceededError(AIAgentError):
    pass


class AIToolValidationError(AIAgentError):
    pass


class AIToolExecutionError(AIAgentError):
    pass
