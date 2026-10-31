# KC library wheel zoom

The library thumbnail grid's `LightboxFeedWheelArea.qml` previously passed every
wheel event to `feed.wheelStep`, including Ctrl+wheel. That scrolls the grid;
it does not change thumbnail size. Ctrl+wheel now calls `kcUi.zoomIn/zoomOut`,
which saves the pending UI scale in QSettings. The existing restart bar applies
that scale at the next launch. Wheel without Ctrl continues scrolling.

The photo viewer has its own Ctrl+wheel photo zoom and is unaffected.
