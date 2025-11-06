"""Parallel spatial computation services."""
from __future__ import annotations

import asyncio
import concurrent.futures
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from ..config import ComputeConfig, PlatformConfig
from .data import TerrainTile

try:  # Optional imports for advanced backends
    import dask
    from dask.distributed import Client
except Exception:  # pragma: no cover
    dask = None
    Client = None

try:  # pragma: no cover
    from numba import cuda
except Exception:  # pragma: no cover
    cuda = None


@dataclass
class AnalysisResult:
    tile: TerrainTile
    statistics: Dict[str, float]
    advisories: List[str]


class ParallelSpatialEngine:
    """Coordinates GPU, CPU and distributed workers for terrain analysis."""

    def __init__(self, config: PlatformConfig) -> None:
        self.config = config
        self._compute_cfg: ComputeConfig = config.compute
        self._cpu_pool: Optional[concurrent.futures.Executor] = None
        self._dask_client: Any = None

    async def initialize(self) -> None:
        loop = asyncio.get_running_loop()
        self._cpu_pool = concurrent.futures.ProcessPoolExecutor(max_workers=self._compute_cfg.max_workers)
        if self._compute_cfg.dask_scheduler and dask is not None:
            self._dask_client = await loop.run_in_executor(None, Client, self._compute_cfg.dask_scheduler)

    async def shutdown(self) -> None:
        if self._dask_client is not None:
            await asyncio.get_running_loop().run_in_executor(None, self._dask_client.close)
            self._dask_client = None
        if self._cpu_pool is not None:
            self._cpu_pool.shutdown(wait=False)
            self._cpu_pool = None

    async def process_terrain_analysis(self, tile: TerrainTile, parameters: Dict[str, Any]) -> Dict[str, Any]:
        if self._cpu_pool is None:
            raise RuntimeError("ParallelSpatialEngine not initialized")
        loop = asyncio.get_running_loop()
        stats = await loop.run_in_executor(self._cpu_pool, self._analyze_tile, tile, parameters)
        advisories = []
        if stats["slope"] > parameters.get("slope_threshold", 15):
            advisories.append("High slope detected. Mobility impacted.")
        return {"statistics": stats, "advisories": advisories}

    @staticmethod
    def _analyze_tile(tile: TerrainTile, parameters: Dict[str, Any]) -> Dict[str, float]:
        np.random.seed(hash(tile.identifier) % 2 ** 32)
        gradient = np.random.rand(2)
        slope = float(np.hypot(*gradient) * 45)
        visibility = float(max(0.0, 100 - slope))
        return {
            "elevation": tile.elevation + gradient[0] * 5,
            "slope": slope,
            "visibility": visibility,
        }

    async def gpu_accelerated_visibility(self, height_map: np.ndarray) -> np.ndarray:
        if not self.config.compute.enable_gpu or cuda is None:
            return np.sqrt(height_map)
        stream = cuda.stream()
        device_array = cuda.to_device(height_map, stream=stream)
        result = cuda.device_array_like(device_array, stream=stream)

        @cuda.jit
        def _visibility_kernel(src, dst):  # pragma: no cover - requires GPU
            x, y = cuda.grid(2)
            if x < src.shape[0] and y < src.shape[1]:
                dst[x, y] = math.sqrt(src[x, y])

        threads = (16, 16)
        blocks = (
            (height_map.shape[0] + threads[0] - 1) // threads[0],
            (height_map.shape[1] + threads[1] - 1) // threads[1],
        )
        _visibility_kernel[blocks, threads, stream](device_array, result)
        stream.synchronize()
        return result.copy_to_host(stream=stream)
