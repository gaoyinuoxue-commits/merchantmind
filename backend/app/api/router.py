from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    agent,
    badcase,
    conversations,
    experiments,
    health,
    knowledge,
    memories,
    merchants,
    monitoring,
    simulator,
    tools,
    traces,
    evaluation,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(simulator.router)
api_router.include_router(conversations.router)
api_router.include_router(memories.router)
api_router.include_router(knowledge.router)
api_router.include_router(tools.router)
api_router.include_router(agent.router)
api_router.include_router(traces.router)
api_router.include_router(evaluation.router)
api_router.include_router(badcase.router)
api_router.include_router(experiments.router)
api_router.include_router(monitoring.router)
api_router.include_router(merchants.router)
