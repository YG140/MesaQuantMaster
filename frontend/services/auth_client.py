from __future__ import annotations

from services.api_client import ApiClient


class AuthClient:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def register(self, name: str, email: str, password: str) -> dict:
        return self.api.post(
            "/auth/register",
            json={"name": name, "email": email, "password": password},
            auth=False,
        )

    def login(self, email: str, password: str) -> dict:
        return self.api.post(
            "/auth/login",
            data={"username": email, "password": password},
            auth=False,
        )

    def me(self) -> dict:
        return self.api.get("/users/me")
