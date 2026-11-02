"""Thin client for the local Ollama API."""
import httpx
from pydantic import BaseModel, Field

DEFAULT_ENDPOINT = "http://localhost:11434"


class OllamaUnavailable(Exception):
    """Ollama could not be reached or did not answer in time."""


class ModelInfo(BaseModel):
    name: str
    size: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    capabilities: list[str] = Field(default_factory=list)

    @property
    def vision(self) -> bool:
        return "vision" in self.capabilities

    @property
    def thinking(self) -> bool:
        return "thinking" in self.capabilities


class ChatResult(BaseModel):
    content: str
    done_reason: str | None = None
    duration_s: float


class OllamaClient:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT, transport: httpx.AsyncBaseTransport | None = None):
        self._http = httpx.AsyncClient(base_url=endpoint, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self._http.get("/api/tags", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailable(str(exc)) from exc
        return [self._to_info(entry) for entry in response.json().get("models", [])]

    @staticmethod
    def _to_info(entry: dict) -> ModelInfo:
        details = entry.get("details") or {}
        return ModelInfo(
            name=entry["name"],
            size=entry.get("size"),
            family=details.get("family"),
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            capabilities=entry.get("capabilities") or [],
        )

    async def chat(self, body: dict, timeout_s: float) -> ChatResult:
        try:
            response = await self._http.post("/api/chat", json=body | {"stream": False}, timeout=timeout_s)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailable(str(exc) or type(exc).__name__) from exc
        data = response.json()
        return ChatResult(
            content=data.get("message", {}).get("content", ""),
            done_reason=data.get("done_reason"),
            duration_s=data.get("total_duration", 0) / 1e9,
        )
