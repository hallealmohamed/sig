"""PyQt5-based GIS application with vector, raster and hexagonal grid support."""
from __future__ import annotations

import math
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MplPolygon
from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:  # lazy imports for heavy libs
    import geopandas as gpd
    import rasterio
    from rasterio import features
    from shapely.geometry import Point, Polygon
except Exception as exc:  # pragma: no cover - handled at runtime
    gpd = None
    rasterio = None
    features = None
    Polygon = None
    Point = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


# --------------------------------------------------------------------------------------
# Helper dataclasses and cache utilities
# --------------------------------------------------------------------------------------


def require_backends() -> None:
    """Ensure the optional geospatial dependencies are present."""
    if IMPORT_ERROR:
        raise RuntimeError(
            "Les dépendances géospatiales (geopandas, rasterio, shapely) sont requises"  # noqa: E501
        ) from IMPORT_ERROR


@dataclass
class LayerStyle:
    color: Union[str, Tuple[float, float, float]] = "#2A9D8F"
    edge_color: Union[str, Tuple[float, float, float]] = "#264653"
    linewidth: float = 1.0
    alpha: float = 0.8


@dataclass
class Layer:
    name: str
    visible: bool = True
    style: LayerStyle = field(default_factory=LayerStyle)

    def draw(self, axes) -> None:  # pragma: no cover - GUI drawing
        raise NotImplementedError


@dataclass
class VectorLayer(Layer):
    data: Optional["gpd.GeoDataFrame"] = None

    def draw(self, axes) -> None:  # pragma: no cover - GUI drawing
        if self.visible and self.data is not None:
            self.data.plot(ax=axes, color=self.style.color, edgecolor=self.style.edge_color, alpha=self.style.alpha)


@dataclass
class RasterLayer(Layer):
    array: Optional[np.ndarray] = None
    transform: Optional["rasterio.Affine"] = None
    cmap: str = "terrain"

    def draw(self, axes) -> None:  # pragma: no cover - GUI drawing
        if self.visible and self.array is not None:
            axes.imshow(
                np.squeeze(self.array),
                cmap=self.cmap,
                extent=self._extent,
                interpolation="nearest",
                origin="upper",
            )

    @property
    def _extent(self) -> Tuple[float, float, float, float]:
        if self.transform is None or self.array is None:
            return (0, 1, 0, 1)
        height, width = self.array.shape[-2:]
        x_min = self.transform.c
        y_max = self.transform.f
        x_max = x_min + width * self.transform.a
        y_min = y_max + height * self.transform.e
        return (x_min, x_max, y_min, y_max)


@dataclass
class Hexagon:
    polygon: "Polygon"
    axial: Tuple[int, int]
    neighbors: List[Tuple[int, int]] = field(default_factory=list)
    stats: Dict[str, float] = field(default_factory=dict)


@dataclass
class HexLayer(Layer):
    hexagons: List[Hexagon] = field(default_factory=list)
    highlighted: Optional[Hexagon] = None

    def draw(self, axes) -> None:  # pragma: no cover - GUI drawing
        if not self.visible:
            return
        for hx in self.hexagons:
            coords = np.asarray(hx.polygon.exterior.coords)
            patch = MplPolygon(
                coords,
                closed=True,
                facecolor=self.style.color,
                edgecolor=self.style.edge_color,
                linewidth=self.style.linewidth,
                alpha=0.3 if hx is not self.highlighted else 0.8,
            )
            axes.add_patch(patch)


class LRUCache:
    """Simple LRU cache used for layer caching."""

    def __init__(self, maxsize: int = 4):
        self.maxsize = maxsize
        self._lock = threading.Lock()
        self._cache: "OrderedDict[str, object]" = OrderedDict()

    def get(self, key: str) -> Optional[object]:
        with self._lock:
            value = self._cache.get(key)
            if value is not None:
                self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: object) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)


# --------------------------------------------------------------------------------------
# Layer manager and map canvas
# --------------------------------------------------------------------------------------


class LayerManager(QObject):
    layers_changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.layers: List[Layer] = []

    def add_layer(self, layer: Layer) -> None:
        self.layers.append(layer)
        self.layers_changed.emit()

    def toggle_visibility(self, layer: Layer) -> None:
        layer.visible = not layer.visible
        self.layers_changed.emit()

    def remove_layer(self, layer: Layer) -> None:
        self.layers.remove(layer)
        self.layers_changed.emit()

    def __iter__(self) -> Iterable[Layer]:
        return iter(self.layers)


class MapCanvas(FigureCanvasQTAgg):
    hex_selected = pyqtSignal(Hexagon)

    def __init__(self, manager: LayerManager) -> None:
        self.figure = Figure(figsize=(6, 6))
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_aspect("equal")
        self.manager = manager
        self.manager.layers_changed.connect(self.redraw)
        self.mpl_connect("button_press_event", self.on_click)
        self._setup_navigation()

    def _setup_navigation(self) -> None:
        self.axes.set_title("SIG Hexagonal")
        self.axes.set_xlabel("X")
        self.axes.set_ylabel("Y")
        self.draw()

    def redraw(self) -> None:
        self.axes.clear()
        for layer in self.manager:
            layer.draw(self.axes)
        self.axes.relim()
        self.axes.autoscale_view()
        self.figure.tight_layout()
        self.draw_idle()

    def on_click(self, event) -> None:  # pragma: no cover - GUI interaction
        if event.inaxes != self.axes:
            return
        for layer in self.manager:
            if isinstance(layer, HexLayer) and layer.visible:
                for hx in layer.hexagons:
                    if hx.polygon.contains(Point(event.xdata, event.ydata)):
                        layer.highlighted = hx
                        self.redraw()
                        self.hex_selected.emit(hx)
                        return


# --------------------------------------------------------------------------------------
# Hexagonal grid generation and statistics
# --------------------------------------------------------------------------------------


class HexGridGenerator:
    def __init__(self, target_size: float = 1000.0) -> None:
        self.target_size = target_size

    def generate(self, bounds: Tuple[float, float, float, float]) -> List[Hexagon]:
        require_backends()
        minx, miny, maxx, maxy = bounds
        width = maxx - minx
        height = maxy - miny
        if width == 0 or height == 0:
            raise ValueError("Les bornes sont invalides pour la génération de grille")
        hex_height = math.sqrt(3) * self.target_size / 2
        hex_width = self.target_size
        cols = int(math.ceil(width / (hex_width * 0.75)))
        rows = int(math.ceil(height / hex_height))
        hexagons: List[Hexagon] = []
        for row in range(rows):
            for col in range(cols):
                center_x = minx + col * hex_width * 0.75
                center_y = miny + row * hex_height
                if col % 2:
                    center_y += hex_height / 2
                polygon = self._create_hexagon(center_x, center_y, self.target_size / 2)
                hexagons.append(Hexagon(polygon=polygon, axial=(col, row)))
        self._assign_neighbors(hexagons)
        return hexagons

    def clip_to_geometry(self, hexagons: List[Hexagon], geometry) -> List[Hexagon]:
        clipped: List[Hexagon] = []
        for hx in hexagons:
            inter = hx.polygon.intersection(geometry)
            if not inter.is_empty:
                hx.polygon = inter
                clipped.append(hx)
        return clipped

    def _create_hexagon(self, cx: float, cy: float, radius: float) -> Polygon:
        angles = np.linspace(0, 2 * math.pi, 7)[:-1]
        points = [(cx + math.cos(a) * radius, cy + math.sin(a) * radius) for a in angles]
        return Polygon(points)

    def _assign_neighbors(self, hexagons: List[Hexagon]) -> None:
        axial_map: Dict[Tuple[int, int], Hexagon] = {hx.axial: hx for hx in hexagons}
        for hx in hexagons:
            q, r = hx.axial
            neighbors = [
                (q + 1, r),
                (q - 1, r),
                (q, r + 1),
                (q, r - 1),
                (q + 1, r - 1),
                (q - 1, r + 1),
            ]
            hx.neighbors = [n for n in neighbors if n in axial_map]

    def compute_statistics(
        self,
        hexagons: List[Hexagon],
        raster_layer: Optional[RasterLayer] = None,
    ) -> None:
        if raster_layer is None or raster_layer.array is None or raster_layer.transform is None:
            return
        array = np.squeeze(raster_layer.array)
        transform = raster_layer.transform
        for hx in hexagons:
            mask = features.geometry_mask([hx.polygon], out_shape=array.shape, transform=transform, invert=True)
            values = array[mask]
            if values.size == 0:
                continue
            zmin = float(np.nanmin(values))
            zmax = float(np.nanmax(values))
            zmean = float(np.nanmean(values))
            slope = float(np.nanstd(values.astype(float)))
            hx.stats.update({"Zmin": zmin, "Zmax": zmax, "Zmean": zmean, "Slope": slope})


# --------------------------------------------------------------------------------------
# Asynchronous loading threads
# --------------------------------------------------------------------------------------


class VectorLoaderThread(QThread):
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, path: Path, cache: LRUCache):
        super().__init__()
        self.path = path
        self.cache = cache

    def run(self) -> None:  # pragma: no cover - uses thread
        try:
            cached = self.cache.get(str(self.path))
            if cached is None:
                data = gpd.read_file(self.path)
                self.cache.set(str(self.path), data)
            else:
                data = cached
            self.loaded.emit(self.path.name, data)
        except Exception as exc:  # pragma: no cover
            self.failed.emit(str(exc))


class RasterLoaderThread(QThread):
    loaded = pyqtSignal(str, object, object)
    failed = pyqtSignal(str)

    def __init__(self, path: Path, cache: LRUCache):
        super().__init__()
        self.path = path
        self.cache = cache

    def run(self) -> None:  # pragma: no cover - uses thread
        try:
            cached = self.cache.get(str(self.path))
            if cached is None:
                with rasterio.open(self.path) as dataset:
                    array = dataset.read(1)
                    transform = dataset.transform
                self.cache.set(str(self.path), (array, transform))
            else:
                array, transform = cached
            self.loaded.emit(self.path.name, array, transform)
        except Exception as exc:  # pragma: no cover
            self.failed.emit(str(exc))


# --------------------------------------------------------------------------------------
# UI components
# --------------------------------------------------------------------------------------


class LayerTree(QTreeWidget):
    layer_toggled = pyqtSignal(Layer)

    def __init__(self, manager: LayerManager):
        super().__init__()
        self.manager = manager
        self.setHeaderHidden(True)
        self.manager.layers_changed.connect(self.refresh)
        self.itemChanged.connect(self._on_item_changed)
        self.refresh()

    def refresh(self) -> None:
        self.blockSignals(True)
        self.clear()
        for layer in self.manager:
            item = QTreeWidgetItem([layer.name])
            item.setCheckState(0, Qt.Checked if layer.visible else Qt.Unchecked)
            item.setData(0, Qt.UserRole, layer)
            self.addTopLevelItem(item)
        self.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        layer = item.data(0, Qt.UserRole)
        if isinstance(layer, Layer):
            layer.visible = item.checkState(0) == Qt.Checked
            self.layer_toggled.emit(layer)
            self.manager.layers_changed.emit()


class InfoPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.label = QLabel("Sélectionnez un hexagone pour voir les statistiques")
        layout.addWidget(self.label)

    def display_hexagon(self, hexagon: Hexagon) -> None:
        stats_lines = [f"{key}: {value:.2f}" for key, value in sorted(hexagon.stats.items())]
        neighbors = ", ".join([f"({q},{r})" for q, r in hexagon.neighbors]) or "Aucun"
        text = [
            f"Axial: {hexagon.axial}",
            f"Voisins: {neighbors}",
        ] + stats_lines
        self.label.setText("\n".join(text))


class ControlPanel(QWidget):
    load_vector = pyqtSignal(Path)
    load_raster = pyqtSignal(Path)
    generate_hex = pyqtSignal(float)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        vector_btn = QPushButton("Charger un vecteur")
        raster_btn = QPushButton("Charger un raster")
        hex_btn = QPushButton("Générer une grille hexagonale")
        self.cache_label = QLabel("Cache: 0 entrées")
        layout.addWidget(vector_btn)
        layout.addWidget(raster_btn)
        layout.addWidget(hex_btn)
        layout.addWidget(self.cache_label)
        vector_btn.clicked.connect(self._choose_vector)
        raster_btn.clicked.connect(self._choose_raster)
        hex_btn.clicked.connect(self._generate_hex)

    def update_cache_size(self, cache: LRUCache) -> None:
        self.cache_label.setText(f"Cache: {len(cache._cache)} entrées")

    def _choose_vector(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un vecteur", filter="Shapefile (*.shp)")
        if path:
            self.load_vector.emit(Path(path))

    def _choose_raster(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un raster", filter="GeoTIFF (*.tif *.tiff)")
        if path:
            self.load_raster.emit(Path(path))

    def _generate_hex(self) -> None:
        self.generate_hex.emit(1000.0)


# --------------------------------------------------------------------------------------
# Main window
# --------------------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SIG Hexagonal - PyQt5")
        require_backends()

        self.manager = LayerManager()
        self.canvas = MapCanvas(self.manager)
        self.layer_tree = LayerTree(self.manager)
        self.info_panel = InfoPanel()
        self.control_panel = ControlPanel()
        self.cache = LRUCache(maxsize=6)
        self.current_raster: Optional[RasterLayer] = None
        self._threads: List[QThread] = []

        splitter = QSplitter()
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(self.control_panel)
        left_layout.addWidget(self.layer_tree)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.info_panel)
        splitter.setSizes([200, 600, 200])

        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Prêt")

        self.control_panel.load_vector.connect(self.load_vector_layer)
        self.control_panel.load_raster.connect(self.load_raster_layer)
        self.control_panel.generate_hex.connect(self.generate_hex_grid)
        self.canvas.hex_selected.connect(self.info_panel.display_hexagon)

    # ----------------------------------------------------------------------------------
    # Loading logic
    # ----------------------------------------------------------------------------------

    def load_vector_layer(self, path: Path) -> None:
        thread = VectorLoaderThread(path, self.cache)
        thread.loaded.connect(self._vector_loaded)
        thread.failed.connect(self._show_error)
        thread.finished.connect(lambda: self._on_thread_finished(thread))
        thread.finished.connect(lambda: self.control_panel.update_cache_size(self.cache))
        self._threads.append(thread)
        thread.start()

    def load_raster_layer(self, path: Path) -> None:
        thread = RasterLoaderThread(path, self.cache)
        thread.loaded.connect(self._raster_loaded)
        thread.failed.connect(self._show_error)
        thread.finished.connect(lambda: self._on_thread_finished(thread))
        thread.finished.connect(lambda: self.control_panel.update_cache_size(self.cache))
        self._threads.append(thread)
        thread.start()

    def _vector_loaded(self, name: str, data) -> None:
        layer = VectorLayer(name=name, data=data)
        self.manager.add_layer(layer)
        self.statusBar().showMessage(f"Vecteur chargé: {name}")

    def _raster_loaded(self, name: str, array, transform) -> None:
        layer = RasterLayer(name=name, array=array, transform=transform)
        self.current_raster = layer
        self.manager.add_layer(layer)
        self.statusBar().showMessage(f"Raster chargé: {name}")

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Erreur de chargement", message)

    def _on_thread_finished(self, thread: QThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        thread.deleteLater()

    # ----------------------------------------------------------------------------------
    # Hex grid generation
    # ----------------------------------------------------------------------------------

    def generate_hex_grid(self, size: float) -> None:
        bounds = self._compute_bounds()
        if bounds is None:
            QMessageBox.warning(self, "Grille hexagonale", "Chargez des données avant de générer une grille")
            return
        generator = HexGridGenerator(target_size=size)
        hexagons = generator.generate(bounds)
        geometry_union = self._union_geometry()
        if geometry_union is not None:
            hexagons = generator.clip_to_geometry(hexagons, geometry_union)
        generator.compute_statistics(hexagons, self.current_raster)
        layer = HexLayer(name="Grille Hexagonale", hexagons=hexagons, style=LayerStyle(color="#E76F51", alpha=0.4))
        self.manager.add_layer(layer)
        self.statusBar().showMessage("Grille hexagonale générée")

    def _compute_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        minx = miny = float("inf")
        maxx = maxy = float("-inf")
        found = False
        for layer in self.manager:
            if isinstance(layer, VectorLayer) and layer.data is not None:
                bounds = layer.data.total_bounds
                minx = min(minx, bounds[0])
                miny = min(miny, bounds[1])
                maxx = max(maxx, bounds[2])
                maxy = max(maxy, bounds[3])
                found = True
            elif isinstance(layer, RasterLayer) and layer.array is not None and layer.transform is not None:
                extent = layer._extent
                minx = min(minx, extent[0])
                maxx = max(maxx, extent[1])
                miny = min(miny, extent[2])
                maxy = max(maxy, extent[3])
                found = True
        if not found:
            return None
        return (minx, miny, maxx, maxy)

    def _union_geometry(self):
        geometries = []
        for layer in self.manager:
            if isinstance(layer, VectorLayer) and layer.data is not None:
                geometries.extend(layer.data.geometry)
        if not geometries:
            return None
        return gpd.GeoSeries(geometries).unary_union


# --------------------------------------------------------------------------------------
# Application entry point
# --------------------------------------------------------------------------------------


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
