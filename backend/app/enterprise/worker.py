"""Run one approved scheduling/worker pass; invoke periodically via approved cron."""

import argparse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import Principal
from app.config import settings
from app.db import make_engine
from .models import SyncJob
from .orchestrator import enqueue_due_sources, run_job, utcnow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("limit must be between 1 and 100")
    config = settings()
    if config.mode != "synthetic":
        parser.error(
            "Install an approved scoped service identity provider before running workers in enterprise mode"
        )
    engine = make_engine(config.database_url)
    actor = Principal("synthetic-approved-worker", "admin")
    with Session(engine) as session:
        enqueue_due_sources(session, actor)
        session.commit()
        now = utcnow()
        jobs = session.scalars(
            select(SyncJob)
            .where(SyncJob.status.in_(["pending", "retry_wait", "running"]))
            .order_by(SyncJob.created_at)
            .limit(args.limit)
        ).all()
        for job in jobs:
            if job.next_attempt_at and job.next_attempt_at > now:
                continue
            run_job(session, job.id, actor)
        print(
            f"Processed up to {args.limit} approved bounded jobs; polling remains opt-in"
        )


if __name__ == "__main__":
    main()
