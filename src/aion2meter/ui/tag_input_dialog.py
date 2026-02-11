"""전투 종료 시 태그 입력 다이얼로그."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TagInputDialog(QDialog):
    """전투 종료 시 세션에 태그를 입력하는 다이얼로그."""

    tag_submitted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("세션 태그")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("세션에 태그를 입력하세요 (보스명, 메모 등):"))

        self._input = QLineEdit()
        self._input.setPlaceholderText("예: 바하무트, 연습")
        self._input.returnPressed.connect(self._submit)
        layout.addWidget(self._input)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("저장")
        save_btn.clicked.connect(self._submit)
        skip_btn = QPushButton("건너뛰기")
        skip_btn.clicked.connect(self._skip)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(skip_btn)
        layout.addLayout(btn_layout)

    def _submit(self) -> None:
        self.tag_submitted.emit(self._input.text().strip())
        self.accept()

    def _skip(self) -> None:
        self.tag_submitted.emit("")
        self.accept()
