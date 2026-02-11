"""세션 리포트 UI + matplotlib 차트."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from aion2meter.io.session_repository import SessionRepository


class SkillBarChart(FigureCanvasQTAgg):
    """스킬별 대미지 수평 막대 차트."""

    def __init__(self, names: list[str], damages: list[int]) -> None:
        fig = Figure(figsize=(5, 3), tight_layout=True)
        fig.set_facecolor("#1a1a1a")
        super().__init__(fig)

        ax = fig.add_subplot(111)
        ax.set_facecolor("#1a1a1a")
        ax.barh(names, damages, color="#00FF64")
        ax.invert_yaxis()
        ax.set_xlabel("대미지", color="white")
        ax.tick_params(colors="white")
        for label in ax.get_yticklabels():
            label.set_color("white")
        for spine in ax.spines.values():
            spine.set_color("#333333")


class SkillPieChart(FigureCanvasQTAgg):
    """스킬별 대미지 비율 파이 차트."""

    _PALETTE = [
        "#00FF64",
        "#FFD700",
        "#FF6B6B",
        "#64B5F6",
        "#BA68C8",
        "#4DB6AC",
        "#FF8A65",
        "#A1887F",
        "#90A4AE",
        "#E0E0E0",
    ]

    def __init__(self, names: list[str], percentages: list[float]) -> None:
        fig = Figure(figsize=(4, 3), tight_layout=True)
        fig.set_facecolor("#1a1a1a")
        super().__init__(fig)

        ax = fig.add_subplot(111)
        colors = [self._PALETTE[i % len(self._PALETTE)] for i in range(len(names))]
        ax.pie(
            percentages,
            labels=names,
            colors=colors,
            autopct="%.1f%%",
            textprops={"color": "white", "fontsize": 8},
        )


class DpsTimelineChart(FigureCanvasQTAgg):
    """DPS 타임라인 라인 차트."""

    def __init__(
        self,
        times: list[float],
        dps_values: list[float],
        avg_dps: float = 0.0,
        peak_dps: float = 0.0,
    ) -> None:
        fig = Figure(figsize=(9, 2.5), tight_layout=True)
        fig.set_facecolor("#1a1a1a")
        super().__init__(fig)

        ax = fig.add_subplot(111)
        ax.set_facecolor("#1a1a1a")
        ax.plot(times, dps_values, color="#00FF64", linewidth=1.2)

        if peak_dps > 0:
            ax.axhline(y=peak_dps, color="#FF6B6B", linestyle="--", linewidth=0.8, label=f"Peak: {peak_dps:,.0f}")
        if avg_dps > 0:
            ax.axhline(y=avg_dps, color="#FFD700", linestyle="--", linewidth=0.8, label=f"Avg: {avg_dps:,.0f}")

        ax.set_xlabel("시간 (초)", color="white")
        ax.set_ylabel("DPS", color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("#333333")
        if peak_dps > 0 or avg_dps > 0:
            ax.legend(loc="upper right", facecolor="#2a2a2a", edgecolor="#555555", labelcolor="white")


class SessionDetailDialog(QDialog):
    """세션 상세 정보 다이얼로그."""

    def __init__(
        self,
        repo: SessionRepository,
        session_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"세션 #{session_id} 상세")
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)

        session = repo.get_session(session_id)
        if session is None:
            layout.addWidget(QLabel("세션을 찾을 수 없습니다."))
            return

        # 요약 정보
        start_str = datetime.fromtimestamp(session["start_time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        duration = session["duration"]
        total_damage = session["total_damage"]
        avg_dps = session["avg_dps"]
        peak_dps = session["peak_dps"]

        summary = QLabel(
            f"시간: {start_str}  |  "
            f"지속시간: {duration:.1f}초  |  "
            f"총 대미지: {total_damage:,}  |  "
            f"DPS: {avg_dps:,.1f}  |  "
            f"Peak: {peak_dps:,.1f}"
        )
        layout.addWidget(summary)

        # DPS 타임라인
        timeline_rows = repo.get_session_timeline(session_id)
        if timeline_rows:
            times = [r["elapsed"] for r in timeline_rows]
            dps_values = [r["dps"] for r in timeline_rows]
            timeline_chart = DpsTimelineChart(
                times, dps_values, avg_dps=avg_dps, peak_dps=peak_dps,
            )
            layout.addWidget(timeline_chart)

        # 스킬 요약 데이터
        skill_rows = repo.get_skill_summary(session_id)
        names = [r["skill"] for r in skill_rows]
        damages = [r["total_damage"] for r in skill_rows]
        total = sum(damages) or 1
        percentages = [d / total * 100 for d in damages]

        # 차트 영역
        chart_layout = QHBoxLayout()
        if names:
            chart_layout.addWidget(SkillBarChart(names, damages))
            chart_layout.addWidget(SkillPieChart(names, percentages))
        layout.addLayout(chart_layout)

        # 닫기 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)


class SessionListDialog(QDialog):
    """저장된 세션 목록 다이얼로그."""

    def __init__(
        self,
        repo: SessionRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("세션 목록")
        self.setMinimumSize(700, 400)

        self._repo = repo
        self._session_ids: list[int] = []

        layout = QVBoxLayout(self)

        # 테이블
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["날짜/시간", "지속시간", "총 대미지", "평균 DPS", "Peak DPS"]
        )
        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._open_detail)
        layout.addWidget(self._table)

        # 버튼 행
        btn_layout = QHBoxLayout()
        detail_btn = QPushButton("상세 보기")
        detail_btn.clicked.connect(self._open_detail)
        compare_btn = QPushButton("비교")
        compare_btn.clicked.connect(self._open_compare)
        delete_btn = QPushButton("삭제")
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(detail_btn)
        btn_layout.addWidget(compare_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(btn_layout)

        self._refresh()

    def _refresh(self) -> None:
        """세션 목록을 DB에서 다시 불러온다."""
        sessions = self._repo.list_sessions()
        self._session_ids = [s["id"] for s in sessions]
        self._table.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            start_str = datetime.fromtimestamp(s["start_time"]).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            self._table.setItem(row, 0, QTableWidgetItem(start_str))
            self._table.setItem(
                row, 1, QTableWidgetItem(f"{s['duration']:.1f}초")
            )
            self._table.setItem(
                row, 2, QTableWidgetItem(f"{s['total_damage']:,}")
            )
            self._table.setItem(
                row, 3, QTableWidgetItem(f"{s['avg_dps']:,.1f}")
            )
            self._table.setItem(
                row, 4, QTableWidgetItem(f"{s['peak_dps']:,.1f}")
            )

    def _selected_ids(self) -> list[int]:
        """선택된 세션 ID 목록을 반환한다."""
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()})
        return [self._session_ids[r] for r in rows if r < len(self._session_ids)]

    def _open_detail(self) -> None:
        """선택된 첫 번째 세션의 상세 다이얼로그를 연다."""
        ids = self._selected_ids()
        if not ids:
            return
        dlg = SessionDetailDialog(self._repo, ids[0], self)
        dlg.exec()

    def _open_compare(self) -> None:
        """선택된 2개 이상 세션을 비교 다이얼로그로 연다."""
        ids = self._selected_ids()
        if len(ids) < 2:
            return
        from aion2meter.ui.session_compare import SessionCompareDialog

        dlg = SessionCompareDialog(self._repo, ids[0], ids[1], parent=self)
        dlg.exec()

    def _delete_selected(self) -> None:
        """선택된 세션을 삭제하고 목록을 갱신한다."""
        ids = self._selected_ids()
        for sid in ids:
            self._repo.delete_session(sid)
        self._refresh()
