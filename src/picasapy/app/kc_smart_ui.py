"""Qt bridge for background KC Smart indexing and searches."""

from __future__ import annotations

import os
import statistics
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Property, QSettings, QTimer, Signal, Slot

from picasapy.kc_smart import SmartIndex


def strong_matches(hits: list[tuple[str, float]]) -> bool:
    """Avoid presenting a flat set of unrelated CLIP guesses as matches."""
    if not hits or hits[0][1] < 0.25:
        return False
    scores = [score for _, score in hits[:50]]
    return len(scores) < 5 or scores[0] - statistics.median(scores) >= 0.045


def result_cards(hits: list[tuple[str, float]]) -> list[dict[str, object]]:
    return [{"path": path, "folder": str(Path(path).parent), "name": Path(path).name, "url": Path(path).as_uri(),
             "score": round(score * 100)} for path, score in hits]


class KcSmartController(QObject):
    message = Signal(str)
    statusChanged = Signal()
    resultsChanged = Signal()
    indexingChanged = Signal()
    _progress = Signal(int, int)
    _updateDone = Signal(object)
    _searchDone = Signal(object, bool)

    def __init__(self, data_dir: str | Path, parent: QObject | None = None,
                 index_factory=SmartIndex) -> None:
        super().__init__(parent)
        self._data_dir = Path(data_dir)
        self._index_factory = index_factory
        self._settings = QSettings("PicasaPy", "PicasaPy")
        self._enabled = self._settings.value("kc/smartIndexing", True, type=bool)
        self._busy = False
        self._stop = threading.Event()
        self._results: list[dict[str, object]] = []
        self._status = "AI index ready"
        self._progress.connect(self._on_progress)
        self._updateDone.connect(self._on_update_done)
        self._searchDone.connect(self._on_search_done)
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.setInterval(2000)
        self._scan_timer.timeout.connect(self._automatic_update)

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property("QVariantList", notify=resultsChanged)
    def results(self) -> list[dict[str, object]]:
        return self._results

    @Property(bool, notify=indexingChanged)
    def indexing(self) -> bool:
        return self._busy

    @Property(bool, notify=indexingChanged)
    def enabled(self) -> bool:
        return self._enabled

    @Slot(bool)
    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._settings.setValue("kc/smartIndexing", enabled)
        self.indexingChanged.emit()
        if not enabled:
            self.cancel()

    @Slot()
    def scanSettled(self) -> None:
        if self._enabled:
            self._scan_timer.start()

    def _automatic_update(self) -> None:
        if self._enabled:
            self.updateIndex()

    @Slot()
    def updateIndex(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._stop.clear()
        self.indexingChanged.emit()
        self._status = "Preparing AI photo index..."
        self.statusChanged.emit()
        self.message.emit(self._status)
        threading.Thread(target=self._update_worker, daemon=True).start()

    @Slot()
    def cancel(self) -> None:
        self._stop.set()

    def _update_worker(self) -> None:
        try:
            if os.name == "nt":
                import ctypes
                kernel = ctypes.windll.kernel32
                kernel.SetThreadPriority(kernel.GetCurrentThread(), -1)
            index = self._index_factory(self._data_dir, sleep_s=0.25)
            stats = index.update(lambda done, total: self._progress.emit(done, total), self._stop)
            if not stats["stopped"] and not self._stop.is_set():
                from .kc_things import update_things
                update_things(index)
            self._updateDone.emit(stats)
        except Exception as exc:  # noqa: BLE001
            self._updateDone.emit(exc)

    @Slot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        self._status = f"Learning your photos: {done}/{total}"
        self.statusChanged.emit()

    @Slot(object)
    def _on_update_done(self, outcome: object) -> None:
        self._busy = False
        self.indexingChanged.emit()
        if isinstance(outcome, Exception):
            self._status = f"AI index failed: {outcome}"
        elif outcome["stopped"]:
            self._status = "AI indexing paused; it will resume next time"
        else:
            self._status = f"AI index updated: {outcome['added']} photos learned"
        self.statusChanged.emit()
        self.message.emit(self._status)

    @Slot(str)
    def search(self, query: str) -> None:
        if query.strip():
            self._status = "Searching photos..."
            self.statusChanged.emit()
            threading.Thread(target=self._search_worker, args=(query, False), daemon=True).start()

    @Slot(str)
    def similar(self, path: str) -> None:
        self._status = "Finding similar photos..."
        self.statusChanged.emit()
        threading.Thread(target=self._search_worker, args=(path, True), daemon=True).start()

    def _search_worker(self, query: str, similar: bool) -> None:
        try:
            index = self._index_factory(self._data_dir)
            hits = index.similar(query, limit=50) if similar else index.search(query, limit=50, min_score=0.0)
            self._searchDone.emit(result_cards(hits) if similar or strong_matches(hits) else [], bool(hits))
        except Exception as exc:  # noqa: BLE001
            self._searchDone.emit(exc, False)

    @Slot(object, bool)
    def _on_search_done(self, outcome: object, had_hits: bool) -> None:
        if isinstance(outcome, Exception):
            self._status = f"AI search failed: {outcome}"
            self._results = []
        else:
            self._results = outcome
            self._status = f"{len(outcome)} matches" if outcome else ("No strong matches" if had_hits else "No indexed photos yet")
        self.resultsChanged.emit()
        self.statusChanged.emit()

    @Slot(str)
    def showThing(self, tag: str) -> None:
        from .kc_things import photos_with_thing
        self._results = result_cards([(r["path"], r["score"])
                                      for r in photos_with_thing(self._data_dir, tag)])
        self._status = f"{tag}: {len(self._results)} photos"
        self.resultsChanged.emit()
        self.statusChanged.emit()

    @Property("QVariantList", notify=resultsChanged)
    def things(self) -> list[dict]:
        from .kc_things import list_things
        return list_things(self._data_dir)
