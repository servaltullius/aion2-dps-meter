"""세션 비교 다이얼로그."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from aion2meter.io.session_repository import SessionRepository


class CompareBarChart(FigureCanvasQTAgg):
    """두 세션의 스킬별 대미지를 나란히 보여주는 수평 막대 차트."""

    def __init__(self, skills_a: list[dict], skills_b: list[dict]) -> None:
        fig = Figure(figsize=(8, 4), facecolor="#1a1a1a")
        super().__init__(fig)

        ax1 = fig.add_subplot(121)
        ax2 = fig.add_subplot(122)

        self._draw_bars(ax1, skills_a, "세션 A", "#00FF64")
        self._draw_bars(ax2, skills_b, "세션 B", "#FFD700")

        fig.tight_layout()

    @staticmethod
    def _draw_bars(
        ax,  # noqa: ANN001
        skills: list[dict],
        title: str,
        color: str,
    ) -> None:
        ax.set_facecolor("#1a1a1a")
        ax.set_title(title, color="white", fontsize=11)

        top = skills[:8]
        names = [s["skill"] for s in top]
        damages = [s["total_damage"] for s in top]

        y_pos = range(len(names))
        ax.barh(y_pos, damages, color=color)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(names, color="white", fontsize=8)
        ax.invert_yaxis()
        ax.tick_params(axis="x", colors="white")

        for spine in ax.spines.values():
            spine.set_color("#333333")


class SessionCompareDialog(QDialog):
    """두 세션을 나란히 비교하는 다이얼로그."""

    def __init__(
        self,
        repo: SessionRepository,
        id_a: int,
        id_b: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"세션 비교: #{id_a} vs #{id_b}")
        self.setMinimumSize(800, 500)

        session_a = repo.get_session(id_a)
        session_b = repo.get_session(id_b)

        if session_a is None or session_b is None:
            return

        skills_a = repo.get_skill_summary(id_a)
        skills_b = repo.get_skill_summary(id_b)

        layout = QVBoxLayout(self)

        # --- 요약 라벨 ---
        dt_a = datetime.fromtimestamp(session_a["start_time"]).strftime("%m/%d %H:%M")
        dt_b = datetime.fromtimestamp(session_b["start_time"]).strftime("%m/%d %H:%M")

        dps_a: float = session_a["avg_dps"]
        dps_b: float = session_b["avg_dps"]
        dps_diff = dps_b - dps_a
        dps_pct = (dps_diff / dps_a * 100) if dps_a else 0.0
        sign = "+" if dps_diff >= 0 else ""

        summary_text = (
            f"A ({dt_a}): DPS {dps_a:,.0f}  |  "
            f"B ({dt_b}): DPS {dps_b:,.0f}  |  "
            f"차이: {sign}{dps_diff:,.0f} ({sign}{dps_pct:.1f}%)"
        )

        summary_label = QLabel(summary_text)
        summary_label.setStyleSheet("font-size: 12px; padding: 8px;")
        layout.addWidget(summary_label)

        # --- 차트 ---
        chart = CompareBarChart(skills_a, skills_b)
        layout.addWidget(chart)

        # --- 닫기 버튼 ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
