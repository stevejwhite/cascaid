"""Prepare classifier embeddings before opening production admission; no trainee data."""

import asyncio

from psychiatry_api.cases import load_cases
from psychiatry_api.config import Settings
from psychiatry_api.models.selection import embedding_model, verify_embedding_service
from psychiatry_api.roleplay.classify import TrainedClassifiers, classifier_cache


async def warm() -> None:
    settings = Settings()
    if not settings.production:
        raise ValueError("Classifier warm-up requires production settings")
    await verify_embedding_service(settings)
    classifiers = TrainedClassifiers(embedding_model(settings), classifier_cache(settings))
    await classifiers.ready({case.id: case for case in load_cases(settings.cases_path)})
    print("Production classifier cache prepared from authored training data.")


if __name__ == "__main__":
    asyncio.run(warm())
