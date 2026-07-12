from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_service import ANALYSIS_TYPES, analyze
from app.auth import get_current_user
from app.database import get_db
from app.models import Analysis, User
from app.templating import templates

router = APIRouter()


def _require_login(user: User | None):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return None


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    redirect = _require_login(user)
    if redirect:
        return redirect
    analyses = db.scalars(
        select(Analysis)
        .where(Analysis.user_id == user.id)
        .order_by(Analysis.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request, "dashboard.html", {"user": user, "analyses": analyses}
    )


@router.get("/analyze", response_class=HTMLResponse)
def analyze_form(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    redirect = _require_login(user)
    if redirect:
        return redirect
    return templates.TemplateResponse(
        request,
        "analyze.html",
        {"user": user, "analysis_types": ANALYSIS_TYPES, "error": None},
    )


@router.post("/analyze")
def run_analysis(
    request: Request,
    title: str = Form("Untitled document"),
    analysis_type: str = Form("summary"),
    source_text: str = Form(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    redirect = _require_login(user)
    if redirect:
        return redirect

    if not source_text.strip():
        return templates.TemplateResponse(
            request,
            "analyze.html",
            {
                "user": user,
                "analysis_types": ANALYSIS_TYPES,
                "error": "Please paste some document text to analyze.",
            },
            status_code=400,
        )

    result = analyze(source_text, analysis_type)
    analysis = Analysis(
        user_id=user.id,
        title=title.strip() or "Untitled document",
        analysis_type=analysis_type,
        source_text=source_text,
        result_text=result.result_text,
        backend=result.backend,
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return RedirectResponse(url=f"/analysis/{analysis.id}", status_code=303)


@router.get("/analysis/{analysis_id}", response_class=HTMLResponse)
def analysis_detail(
    analysis_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    redirect = _require_login(user)
    if redirect:
        return redirect
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != user.id:
        return templates.TemplateResponse(
            request, "not_found.html", {"user": user}, status_code=404
        )
    return templates.TemplateResponse(
        request,
        "analysis_detail.html",
        {"user": user, "analysis": analysis, "analysis_types": ANALYSIS_TYPES},
    )
