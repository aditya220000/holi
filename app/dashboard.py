from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics import aggregate_topic_performance, latest_metric_for_reel, metric_quality_score
from app.config import settings
from app.database import get_db
from app.models import Reel
from app.script_generator import MASTER_SCRIPT_PROMPT
from app.tasks import regenerate_reel_task

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.post("/regenerate/{reel_id}")
def regenerate_from_dashboard(reel_id: UUID, db: Session = Depends(get_db)) -> RedirectResponse:
    reel = db.get(Reel, reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    regenerate_reel_task.delay(str(reel.id))
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)) -> str:
    reels = db.scalars(select(Reel).order_by(Reel.created_at.desc()).limit(30)).all()
    topic_perf = aggregate_topic_performance(db)

    rows = []
    for reel in reels:
        metric = latest_metric_for_reel(db, reel.id)
        metric_summary = "n/a"
        if metric:
            metric_summary = (
                f"Views: {metric.views} | Watch: {metric.watch_time_pct:.1f}% | "
                f"Saves: {metric.saves} | Shares: {metric.shares} | Score: {metric_quality_score(metric):.2f}"
            )

        rows.append(
            "<tr>"
            f"<td>{reel.created_at:%Y-%m-%d %H:%M}</td>"
            f"<td>{reel.id}</td>"
            f"<td>{reel.topic.value}</td>"
            f"<td>{reel.status.value}</td>"
            f"<td>{float(reel.virality_score):.2f}</td>"
            f"<td>{metric_summary}</td>"
            f"<td><form method='post' action='/dashboard/regenerate/{reel.id}'><button type='submit'>Regenerate Better Script</button></form></td>"
            "</tr>"
        )

    topic_items = "".join(
        [f"<li>{topic}: avg watch {score:.2f}%</li>" for topic, score in topic_perf.items()]
    )

    return f"""
    <html>
      <head>
        <title>{settings.app_name} Dashboard</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 24px; background: #f5f7fb; color: #101828; }}
          h1 {{ margin-bottom: 8px; }}
          .panel {{ background: #fff; border: 1px solid #d0d5dd; padding: 16px; border-radius: 8px; margin-bottom: 18px; }}
          table {{ width: 100%; border-collapse: collapse; background: #fff; }}
          th, td {{ border: 1px solid #eaecf0; padding: 10px; font-size: 14px; vertical-align: top; }}
          th {{ background: #f2f4f7; text-align: left; }}
          button {{ background: #111827; color: #fff; border: none; padding: 8px 12px; border-radius: 6px; cursor: pointer; }}
          code {{ font-size: 12px; }}
        </style>
      </head>
      <body>
        <h1>{settings.app_name}</h1>
        <div class="panel">
          <h3>Master Script Prompt (active)</h3>
          <pre style="white-space:pre-wrap;font-size:12px;">{MASTER_SCRIPT_PROMPT}</pre>
        </div>

        <div class="panel">
          <h3>Topic Performance Feedback Loop</h3>
          <ul>{topic_items}</ul>
        </div>

        <table>
          <thead>
            <tr>
              <th>Created</th>
              <th>Reel ID</th>
              <th>Topic</th>
              <th>Status</th>
              <th>Virality</th>
              <th>Performance</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows) if rows else '<tr><td colspan="7">No reels yet.</td></tr>'}
          </tbody>
        </table>
      </body>
    </html>
    """
