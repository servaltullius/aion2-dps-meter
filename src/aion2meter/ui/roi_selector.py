"""ROI 선택 위젯."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from aion2meter.models import ROI


class RoiSelector(QWidget):
    """전체화면 오버레이에서 마우스 드래그로 ROI를 선택한다."""

    roi_selected = pyqtSignal(object)  # ROI

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 전체 화면 크기
        screen = QApplication.primaryScreen()
        if screen is not None:
            geom = screen.geometry()
            self.setGeometry(geom)
        else:
            self.setGeometry(0, 0, 1920, 1080)

        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self._selection: QRect | None = None

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        # 반투명 배경
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self._selection is not None and not self._selection.isNull():
            # 선택 영역은 투명하게
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._selection, QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 선택 영역 테두리
            pen = QPen(QColor(0, 255, 100), 2)
            painter.setPen(pen)
            painter.drawRect(self._selection)

            # 크기 표시
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Consolas", 10))
            text = f"{self._selection.width()} x {self._selection.height()}"
            painter.drawText(
                self._selection.bottomRight() + QPoint(5, 15),
                text,
            )

        # 안내 텍스트
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("맑은 고딕", 14))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
            "전투 채팅창 영역을 드래그하세요 (ESC: 취소)",
        )

    def mousePressEvent(self, event: object) -> None:
        if hasattr(event, "position"):
            self._start = event.position().toPoint()
            self._end = self._start
            self._selection = QRect(self._start, self._end).normalized()
            self.update()

    def mouseMoveEvent(self, event: object) -> None:
        if self._start is not None and hasattr(event, "position"):
            self._end = event.position().toPoint()
            self._selection = QRect(self._start, self._end).normalized()
            self.update()

    def mouseReleaseEvent(self, event: object) -> None:
        if self._selection is not None and self._selection.width() > 10 and self._selection.height() > 10:
            roi = ROI(
                left=self._selection.x(),
                top=self._selection.y(),
                width=self._selection.width(),
                height=self._selection.height(),
            )
            self.roi_selected.emit(roi)
        self.close()

    def keyPressEvent(self, event: object) -> None:
        if hasattr(event, "key") and event.key() == Qt.Key.Key_Escape:
            self.close()
