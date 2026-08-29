from dataclasses import dataclass

from smoodl.api.presenter import JobPresenter
from smoodl.config import Settings
from smoodl.extractors import ExtractorRegistry, GalleryDlExtractor, YtDlpExtractor
from smoodl.services.jobs import JobService
from smoodl.services.materializer import DefaultMaterializer, Materializer
from smoodl.services.process import CommandRunner
from smoodl.services.selector import VariantSelector
from smoodl.services.tokens import TokenService
from smoodl.storage.base import ArtifactStorage
from smoodl.storage.local import LocalArtifactStorage
from smoodl.stores.base import JobStore
from smoodl.stores.memory import InMemoryJobStore


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    store: JobStore
    storage: ArtifactStorage
    extractors: ExtractorRegistry
    jobs: JobService
    tokens: TokenService
    presenter: JobPresenter

    @classmethod
    def build(cls, settings: Settings | None = None) -> "AppContainer":
        resolved = settings or Settings()
        runner = CommandRunner()
        store = InMemoryJobStore()
        storage = LocalArtifactStorage(resolved.artifact_dir)
        registry = ExtractorRegistry(
            [
                YtDlpExtractor(resolved, runner),
                GalleryDlExtractor(resolved, runner),
            ]
        )
        tokens = TokenService(resolved.signing_secret)
        materializer = DefaultMaterializer(resolved, runner, storage)
        jobs = JobService(store, registry, VariantSelector(), materializer)
        return cls(
            settings=resolved,
            store=store,
            storage=storage,
            extractors=registry,
            jobs=jobs,
            tokens=tokens,
            presenter=JobPresenter(resolved, tokens),
        )

    @classmethod
    def for_testing(
        cls,
        *,
        settings: Settings,
        extractors: ExtractorRegistry,
        materializer: Materializer,
    ) -> "AppContainer":
        store = InMemoryJobStore()
        storage = LocalArtifactStorage(settings.artifact_dir)
        tokens = TokenService(settings.signing_secret)
        jobs = JobService(store, extractors, VariantSelector(), materializer)
        return cls(
            settings=settings,
            store=store,
            storage=storage,
            extractors=extractors,
            jobs=jobs,
            tokens=tokens,
            presenter=JobPresenter(settings, tokens),
        )
