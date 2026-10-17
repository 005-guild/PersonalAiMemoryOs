"""Application factory and resource lifecycle."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from threading import RLock

from fastapi import FastAPI
from app.web.routes import install_web
from app import config as configuration

from app.agents.configuration import AIRegistry
from app.agents.generation_gate import GenerationGate
from app.agents.transport import ModelClient
from app.api.health import router as health_router
from app.api.imports import router as imports_router
from app.api.content import router as content_router
from app.api.sync import router as sync_router
from app.api.processing import router as processing_router
from app.api.rag import router as rag_router
from app.api.ui import router as ui_router
from app.api.settings import router as settings_router
from app.api.settings_security import ConfigurationNoStoreMiddleware, configuration_guard
from app.config import Settings
from app.repositories.database import Database
from app.repositories.migrations import check_schema
from app.services.sync import Synchronizer
from app.services.sync_worker import SyncWorker
from app.services.processing import ProcessingService
from app.services.rag_answer import RagAnswerService
from app.services.rag_index import RagIndexService
from app.services.rag_search import RagSearchService
from app.services.rag_worker import RagWorker
from app.services.ai_settings import AISettingsService
from app.services.configuration_files import recover_ai_settings
from app.vector.configuration import EmbeddingRegistry
from app.vector.embedding import EmbeddingClient
from app.vector.qdrant import QdrantClient

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, model_client=None,
               embedding_client=None, qdrant_client=None) -> FastAPI:
    """Create an isolated application; initialize resources only on startup."""
    if settings is None:
        recover_ai_settings(configuration.PROJECT_ROOT)
        settings = Settings()
    elif recover_ai_settings(settings.runtime_root):
        # Injected settings may have been read before an interrupted file commit.
        raise RuntimeError("配置写入已恢复，请重新加载 Settings 后再启动服务。")
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Apply the setting to this application's logs even if logging is configured.
    logging.getLogger("app").setLevel(settings.log_level)
    database = Database(settings.database_url)
    sync_lock = RLock()
    synchronizer = Synchronizer(database, settings, sync_lock)
    worker = SyncWorker(synchronizer, settings.sync_interval)
    registry = AIRegistry(settings)
    ai_settings = AISettingsService(settings, registry=registry)
    model_client = model_client if model_client is not None else ModelClient()
    generation_gate = GenerationGate()
    processing = ProcessingService(database, sync_lock, registry, model_client, generation_gate)
    embedding_registry = EmbeddingRegistry(settings)
    embedding_client = embedding_client if embedding_client is not None else EmbeddingClient()
    qdrant_client = qdrant_client if qdrant_client is not None else QdrantClient(settings.rag_qdrant_url)
    indexer = RagIndexService(database, sync_lock, settings, embedding_registry, embedding_client, qdrant_client)
    rag_worker = RagWorker(indexer, settings.rag_interval)
    rag_search = RagSearchService(indexer, embedding_registry, embedding_client, qdrant_client)
    rag_answer = RagAnswerService(rag_search, registry, model_client, generation_gate)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            try:
                database.initialize()
                check_schema(database.engine)
                await asyncio.to_thread(processing.recover_interrupted)
                await asyncio.to_thread(indexer.recover_interrupted)
            except Exception as exc:
                logger.error("Database startup failed (%s).", type(exc).__name__)
                raise RuntimeError(
                    "Database startup failed; check storage and run alembic upgrade head."
                ) from None
            if settings.sync_enabled:
                worker.start()
            if settings.rag_enabled:
                rag_worker.start()
            logger.info("Personal AI Memory OS started.")
            yield
        finally:
            try:
                await asyncio.gather(processing.close(), rag_answer.close(), rag_worker.stop())
            finally:
                try:
                    await indexer.close()
                finally:
                    try:
                        await worker.stop()
                    finally:
                        try:
                            await asyncio.gather(*(
                                client.aclose() for client in (model_client, embedding_client, qdrant_client)
                                if hasattr(client, "aclose")
                            ))
                        finally:
                            database.dispose()
                            logger.info("Database connections released.")

    app = FastAPI(
        title="Personal AI Memory OS",
        version="0.6.6",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.sync_lock = sync_lock
    app.state.synchronizer = synchronizer
    app.state.sync_worker = worker
    app.state.ai_registry = registry
    app.state.ai_settings = ai_settings
    app.state.configuration_guard = configuration_guard
    app.state.model_client = model_client
    app.state.processing = processing
    app.state.generation_gate = generation_gate
    app.state.embedding_registry = embedding_registry
    app.state.embedding_client = embedding_client
    app.state.qdrant_client = qdrant_client
    app.state.rag_index = indexer
    app.state.rag_worker = rag_worker
    app.state.rag_search = rag_search
    app.state.rag_answer = rag_answer
    app.include_router(health_router)
    app.include_router(content_router)
    app.include_router(sync_router)
    app.include_router(imports_router)
    app.include_router(processing_router)
    app.include_router(rag_router)
    app.include_router(ui_router)
    app.include_router(settings_router)
    app.add_middleware(ConfigurationNoStoreMiddleware)
    install_web(app)
    return app
