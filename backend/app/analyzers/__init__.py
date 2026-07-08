from .base import Analyzer
from .l1_aigen import AiGenAnalyzer
from .l2_forensics import ForensicsAnalyzer
from .l3_recapture import RecaptureAnalyzer
from .l4_metadata import MetadataAnalyzer
from .l5_context import ContextAnalyzer

ALL_ANALYZERS: list[type[Analyzer]] = [
    AiGenAnalyzer,
    ForensicsAnalyzer,
    RecaptureAnalyzer,
    MetadataAnalyzer,
    ContextAnalyzer,
]

__all__ = ["Analyzer", "ALL_ANALYZERS"]
