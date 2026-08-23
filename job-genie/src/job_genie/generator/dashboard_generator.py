import datetime
from pathlib import Path
from typing import Any

from job_genie.generator.canvas_manager import CanvasManager
from job_genie.generator.vault_manager import VaultManager
from job_genie.utils.logger import get_logger

logger = get_logger(__name__)

APPLIED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_MONTH_BARS = 12
MAX_WEEK_BARS = 12
BAR_WIDTH = 110
BAR_GAP = 20
MAX_BAR_HEIGHT = 260
MIN_BAR_HEIGHT = 40


class DashboardGenerator:
    """Generates Dashboard.canvas: a bar-chart breakdown of applications by month and week,
    built from each job's `applied_at` timestamp."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.vault_manager = VaultManager(config)
        self.canvas_manager = CanvasManager()

    def generate(self, db: Any | None) -> Path:
        """Generate the Dashboard.canvas file in the vault root.

        Args:
            db: DatabaseManager to read applied_at timestamps from. If None (or no
                applications are tracked yet), the canvas explains that instead of
                showing empty charts.
        """
        logger.info("Generating Dashboard.canvas...")
        self.canvas_manager = CanvasManager()

        applied_dates = self._get_applied_dates(db)
        monthly = self._monthly_counts(applied_dates)
        weekly = self._weekly_counts(applied_dates)

        y = self._add_summary(applied_dates, monthly)
        y = self._add_bar_chart("Applications by Month", monthly, y, color="4")
        self._add_bar_chart("Applications by Week", weekly, y, color="6")

        dashboard_path = self.vault_manager.vault_path / "Dashboard.canvas"
        self.canvas_manager.save_to_file(dashboard_path)
        logger.info(f"Dashboard generated at: {dashboard_path}")
        return dashboard_path

    def _get_applied_dates(self, db: Any | None) -> list[datetime.datetime]:
        """Reads every job's applied_at timestamp from the DB, skipping unapplied/unparseable rows."""
        if not db:
            return []
        dates = []
        for job in db.get_all_jobs(limit=10000):
            raw = job.get("applied_at")
            if not raw:
                continue
            try:
                dates.append(datetime.datetime.strptime(raw, APPLIED_AT_FORMAT))
            except ValueError:
                logger.warning(f"Could not parse applied_at '{raw}' for job {job.get('id')}")
        return dates

    def _monthly_counts(self, dates: list[datetime.datetime]) -> list[tuple[str, int]]:
        """Buckets dates into a continuous month-by-month timeline (no gaps), capped to the
        most recent MAX_MONTH_BARS months so the chart stays readable."""
        if not dates:
            return []

        def next_month(d: datetime.datetime) -> datetime.datetime:
            return d.replace(year=d.year + 1, month=1) if d.month == 12 else d.replace(month=d.month + 1)

        start = min(dates).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = max(dates).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        months = []
        cur = start
        while cur <= end:
            months.append(cur)
            cur = next_month(cur)
        months = months[-MAX_MONTH_BARS:]

        counts = dict.fromkeys(months, 0)
        for d in dates:
            key = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if key in counts:
                counts[key] += 1

        return [(m.strftime("%b %Y"), counts[m]) for m in months]

    def _weekly_counts(self, dates: list[datetime.datetime]) -> list[tuple[str, int]]:
        """Buckets dates into continuous Monday-start weeks, capped to the most recent
        MAX_WEEK_BARS weeks."""
        if not dates:
            return []

        def week_start(d: datetime.datetime) -> datetime.datetime:
            return (d - datetime.timedelta(days=d.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

        start = week_start(min(dates))
        end = week_start(max(dates))

        weeks = []
        cur = start
        while cur <= end:
            weeks.append(cur)
            cur += datetime.timedelta(days=7)
        weeks = weeks[-MAX_WEEK_BARS:]

        counts = dict.fromkeys(weeks, 0)
        for d in dates:
            ws = week_start(d)
            if ws in counts:
                counts[ws] += 1

        return [(w.strftime("%b %d"), counts[w]) for w in weeks]

    def _add_summary(self, dates: list[datetime.datetime], monthly: list[tuple[str, int]]) -> int:
        """Adds the title/stats text node. Returns the y-coordinate just below it."""
        lines = ["# 📊 Application Insights", ""]

        if not dates:
            lines.append(
                "No applications tracked yet - check the `applied` box on a job note "
                "(or set its `status` to Applied) and run `sync` to start populating this."
            )
        else:
            now = datetime.datetime.now()
            this_month_count = sum(1 for d in dates if d.year == now.year and d.month == now.month)
            week_cutoff = now - datetime.timedelta(days=now.weekday())
            week_cutoff = week_cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
            this_week_count = sum(1 for d in dates if d >= week_cutoff)

            lines.append(f"**{len(dates)}** total applications tracked")
            lines.append(f"**{this_month_count}** this month · **{this_week_count}** this week")

            if monthly:
                busiest_label, busiest_count = max(monthly, key=lambda pair: pair[1])
                if busiest_count > 0:
                    lines.append(f"Busiest month: **{busiest_label}** ({busiest_count} applications)")

        text = "\n".join(lines)
        self.canvas_manager.add_node(node_type="text", x=0, y=0, width=900, height=140, text=text, color="1")
        return 180

    def _add_bar_chart(self, title: str, data: list[tuple[str, int]], top_y: int, color: str) -> int:
        """Adds a bar-chart section (heading + one bar per period) starting at top_y.
        Returns the y-coordinate just below the section, for stacking further sections."""
        self.canvas_manager.add_node(node_type="text", x=0, y=top_y, width=900, height=40, text=f"## {title}")

        if not data:
            self.canvas_manager.add_node(node_type="text", x=0, y=top_y + 50, width=400, height=40, text="No data yet.")
            return top_y + 120

        chart_top = top_y + 50
        baseline = chart_top + MAX_BAR_HEIGHT
        max_count = max(count for _, count in data)

        x = 0
        for label, count in data:
            height = (
                MIN_BAR_HEIGHT if max_count == 0 else max(MIN_BAR_HEIGHT, round((count / max_count) * MAX_BAR_HEIGHT))
            )
            self.canvas_manager.add_node(
                node_type="text",
                x=x,
                y=baseline - height,
                width=BAR_WIDTH,
                height=height,
                text=f"**{count}**",
                color=color,
            )
            self.canvas_manager.add_node(node_type="text", x=x, y=baseline + 10, width=BAR_WIDTH, height=30, text=label)
            x += BAR_WIDTH + BAR_GAP

        return baseline + 70
