"""KC Smart Search: find photos by a plain-English description, offline.

CLIP (ViT-B/32, ONNX, CPU) embeds every photo once; a text query is embedded
the same way and ranked by cosine similarity. See MODELS.md for the model.
"""

from .index import SmartIndex
from .model import ClipEncoder, Encoder, ensure_models

__all__ = ["ClipEncoder", "Encoder", "SmartIndex", "ensure_models"]
