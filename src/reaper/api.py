from __future__ import annotations

from pathlib import Path
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reaper.config import ReaperConfig, load_config
from reaper.domain import ActionStatus
from reaper.engine import ReaperEngine
from reaper.reporting import build_daily_report


def create_app(config: ReaperConfig | None = None, workspace: str | Path | None = None) -> FastAPI:
    root = Path(workspace or Path(__file__).resolve().parents[2]).resolve()
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    app = FastAPI(
        title="Reaper",
        version="0.1.0",
        description="Debt operations agent API and approval console.",
    )
    app.mount(
        "/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static"
    )
    resolved_config = config or load_config()
    engine = ReaperEngine(resolved_config, root)
    app.state.engine = engine

    def get_engine() -> ReaperEngine:
        return cast(ReaperEngine, app.state.engine)

    @app.get("/healthz")
    def healthz(service: ReaperEngine = Depends(get_engine)) -> dict[str, object]:
        return {"status": "ok", "agent": service.config.agent.name, "schema": 1}

    @app.get("/api/summary")
    def summary(service: ReaperEngine = Depends(get_engine)) -> dict[str, object]:
        report = build_daily_report(service.config, service.db)
        return {
            "report": report.model_dump(mode="json"),
            "counts": service.db.summary_counts(),
        }

    @app.get("/api/actions")
    def actions(
        service: ReaperEngine = Depends(get_engine),
        status: ActionStatus | None = None,
    ) -> list[dict[str, object]]:
        return [item.model_dump(mode="json") for item in service.db.list_actions(status)]

    @app.post("/api/actions/{action_id}/approve")
    def approve_action(
        action_id: str,
        actor: str,
        service: ReaperEngine = Depends(get_engine),
        reason: str | None = None,
    ) -> dict[str, object]:
        try:
            action = service.approve(action_id, actor=actor, reason=reason)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return action.model_dump(mode="json")

    @app.post("/api/actions/{action_id}/reject")
    def reject_action(
        action_id: str,
        actor: str,
        service: ReaperEngine = Depends(get_engine),
        reason: str | None = None,
    ) -> dict[str, object]:
        try:
            action = service.reject(action_id, actor=actor, reason=reason)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return action.model_dump(mode="json")

    @app.post("/api/actions/{action_id}/execute")
    def execute_action(
        action_id: str,
        service: ReaperEngine = Depends(get_engine),
    ) -> dict[str, object]:
        try:
            return service.execute(action_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (KeyError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        service: ReaperEngine = Depends(get_engine),
    ) -> HTMLResponse:
        report = build_daily_report(service.config, service.db)
        pending = service.db.list_actions(ActionStatus.PROPOSED)
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "agent": service.config.agent.name,
                "report": report,
                "pending": pending,
                "counts": service.db.summary_counts(),
            },
        )

    @app.post("/actions/{action_id}/decision")
    def dashboard_decision(
        action_id: str,
        decision: Annotated[str, Form()],
        actor: Annotated[str, Form()] = "operator",
        service: ReaperEngine = Depends(get_engine),
    ) -> RedirectResponse:
        if decision == "approve":
            service.approve(action_id, actor=actor)
        elif decision == "reject":
            service.reject(action_id, actor=actor)
        else:
            raise HTTPException(status_code=400, detail="Unknown decision")
        return RedirectResponse(url="/", status_code=303)

    return app
