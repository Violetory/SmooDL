import pytest

from smoodl.domain import JobOptions, MediaVariant, WatermarkPolicy, WatermarkState
from smoodl.errors import SmooDLError
from smoodl.services.selector import VariantSelector


def test_selector_prefers_clean_variant_before_resolution() -> None:
    variants = [
        MediaVariant(
            url="https://cdn.example/high.jpg",
            width=4000,
            height=4000,
            watermark=WatermarkState.PLATFORM,
        ),
        MediaVariant(
            url="https://cdn.example/clean.jpg",
            width=3000,
            height=3000,
            watermark=WatermarkState.NONE,
        ),
    ]

    selected = VariantSelector().select(variants, JobOptions())

    assert selected.url.endswith("clean.jpg")


def test_selector_can_require_explicitly_clean_variant() -> None:
    variants = [MediaVariant(url="https://cdn.example/image.jpg")]

    with pytest.raises(SmooDLError) as raised:
        VariantSelector().select(
            variants,
            JobOptions(watermark_policy=WatermarkPolicy.REQUIRE_CLEAN),
        )

    assert raised.value.code == "CLEAN_VARIANT_UNAVAILABLE"
