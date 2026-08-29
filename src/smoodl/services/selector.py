from smoodl.domain import JobOptions, MediaVariant, QualityPolicy, WatermarkPolicy
from smoodl.errors import SmooDLError


class VariantSelector:
    def select(self, variants: list[MediaVariant], options: JobOptions) -> MediaVariant:
        if not variants:
            raise SmooDLError("EXTRACTOR_FAILED", "No media variants are available", 422)

        candidates = variants
        if options.watermark_policy == WatermarkPolicy.REQUIRE_CLEAN:
            candidates = [item for item in candidates if item.watermark == "none"]
            if not candidates:
                raise SmooDLError(
                    "CLEAN_VARIANT_UNAVAILABLE",
                    "No explicitly watermark-free representation is available",
                    422,
                )

        def score(item: MediaVariant) -> tuple[int, int, int, int, int]:
            clean = int(
                options.watermark_policy == WatermarkPolicy.ALLOW_ANY or item.watermark == "none"
            )
            mp4 = int(item.container in {"mp4", "m4v", "mov"})
            if options.quality == QualityPolicy.PREFER_MP4:
                clean, mp4 = mp4, clean
            pixels = (item.width or 0) * (item.height or 0)
            return clean, pixels, item.bitrate or 0, item.file_size or 0, mp4

        return max(candidates, key=score)
