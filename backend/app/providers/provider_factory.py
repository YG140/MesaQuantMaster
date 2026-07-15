from app.providers.brapi_provider import BrapiProvider


class ProviderFactory:
    @staticmethod
    def get_provider():
        return BrapiProvider()
