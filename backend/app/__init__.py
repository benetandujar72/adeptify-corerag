"""IA Nou Patufet — backend RAG self-hosted multi-agent.

Paquet principal de l'aplicació FastAPI. Tota la inferència LLM passa per un
client OpenAI-compatible (Ollama en dev, vLLM en GPU); mai es criden APIs
comercials de tercers.
"""

__version__ = "0.1.0-mvp"
