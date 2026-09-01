from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from reaper.api import create_app
from reaper.config import ReaperConfig


def test_health_and_dashboard(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    client = TestClient(create_app(config, workspace))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["agent"] == "Reaper"
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "Pending approvals" in dashboard.text


def test_actions_endpoint(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    app = create_app(config, workspace)
    app.state.engine.run_skills()
    client = TestClient(app)
    response = client.get("/api/actions", params={"status": "proposed"})
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_api_approval_and_rejection(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    app = create_app(config, workspace)
    app.state.engine.run_skills()
    pending = app.state.engine.db.list_actions()
    client = TestClient(app)
    approved = client.post(
        f"/api/actions/{pending[0].id}/approve",
        params={"actor": "operator", "reason": "reviewed"},
    )
    rejected = client.post(
        f"/api/actions/{pending[1].id}/reject",
        params={"actor": "operator"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert rejected.json()["status"] == "rejected"
    conflict = client.post(f"/api/actions/{pending[0].id}/approve", params={"actor": "operator"})
    assert conflict.status_code == 409


def test_dashboard_form_decision(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    app = create_app(config, workspace)
    app.state.engine.run_skills()
    action = app.state.engine.db.list_actions()[0]
    client = TestClient(app)
    response = client.post(
        f"/actions/{action.id}/decision",
        data={"decision": "approve", "actor": "operator"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_api_execute_blocks_unapproved_action(config: ReaperConfig) -> None:
    workspace = Path(__file__).resolve().parents[1]
    app = create_app(config, workspace)
    app.state.engine.run_skills()
    action = app.state.engine.db.list_actions()[0]
    client = TestClient(app)
    response = client.post(f"/api/actions/{action.id}/execute")
    assert response.status_code == 403
