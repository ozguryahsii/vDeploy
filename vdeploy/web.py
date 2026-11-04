from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, auth, config, importer, jira_client, mailer, metrics, report, scheduler, settings_store
from .db import SessionLocal, get_db, init_db
from .models import OUTCOMES, ChangeRequest, SyncLog

BASE = Path(__file__).parent
log = logging.getLogger("vdeploy")
templates = Jinja2Templates(directory=str(BASE / "templates"))


# ---------- şablon yardımcıları ----------
def _fmt_dt(value, fmt="%d.%m.%Y %H:%M"):
    return value.strftime(fmt) if value else "—"


def _fmt_hours(h):
    if h is None:
        return "—"
    sign = "-" if h < 0 else ""
    h = abs(h)
    if h < 24:
        return f"{sign}{h:.1f} sa".replace(".", ",")
    days, rest = divmod(h, 24)
    return f"{sign}{int(days)} g {int(rest)} sa"


def _fmt_num(v, suffix=""):
    if v is None:
        return "—"
    s = f"{v:,.1f}" if isinstance(v, float) and not v.is_integer() else f"{int(v):,}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + suffix


templates.env.filters.update(dt=_fmt_dt, hours=_fmt_hours, num=_fmt_num)
templates.env.globals.update(OUTCOMES=OUTCOMES, DAY_NAMES=settings_store.DAY_NAMES, version=__version__)


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append({"kind": kind, "message": message})


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    ctx.setdefault("flashes", request.session.pop("flash", []))
    ctx.setdefault("user", request.session.get("user"))
    return templates.TemplateResponse(request, name, ctx)


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ---------- uygulama ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="vDeploy", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

PUBLIC_PREFIXES = ("/static", "/login", "/health")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """AD girişi açıksa oturum ister; kapalıysa herkes doğrudan girer."""
    path = request.url.path
    if not path.startswith(PUBLIC_PREFIXES):
        with SessionLocal() as db:
            values = settings_store.get_all(db)
        if auth.enabled(values) and not request.session.get("user"):
            return RedirectResponse(f"/login?next={path}", status_code=303)
    return await call_next(request)


# SessionMiddleware, require_login'den sonra eklenir ki onu sarmalasın (önce çalışsın).
app.add_middleware(SessionMiddleware, secret_key=config.secret_key(), session_cookie="vdeploy",
                   max_age=12 * 3600, same_site="lax")


@app.get("/health")
def health():
    return {"ok": True, "version": __version__}


# ---------- giriş ----------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", db: Session = Depends(get_db)):
    if not auth.enabled(settings_store.get_all(db)):
        return back("/")
    return render(request, "login.html", next=next)


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/"),
          db: Session = Depends(get_db)):
    result = auth.authenticate(settings_store.get_all(db), username, password)
    if not result.ok:
        return render(request, "login.html", next=next, error=result.error, username=username)
    request.session["user"] = {"username": result.username, "name": result.display_name}
    return back(next if next.startswith("/") else "/")


@app.get("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return back("/login")


# ---------- dashboard ----------
RANGE_PRESETS = {"4w": ("Son 4 hafta", 4), "8w": ("Son 8 hafta", 8), "13w": ("Son 3 ay", 13),
                 "26w": ("Son 6 ay", 26), "all": ("Tümü", None)}


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _filtered_query(db: Session, request_type: str = "", department: str = "", application: str = ""):
    q = db.query(ChangeRequest)
    if request_type:
        q = q.filter(ChangeRequest.request_type == request_type)
    if department:
        q = q.filter(ChangeRequest.department == department)
    if application:
        q = q.filter(ChangeRequest.application == application)
    return q


def _distinct(db: Session, column) -> list[str]:
    return [v for (v,) in db.query(column).distinct().order_by(column) if v]


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, range: str = "8w", start: str = "", end: str = "", request_type: str = "",
              department: str = "", application: str = "", db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    window = settings_store.window(values)
    rows = _filtered_query(db, request_type, department, application).all()

    today = date.today()
    s, e = _parse_date(start), _parse_date(end)
    if s or e:
        range = "custom"
        s = s or date(2000, 1, 1)
        e = e or today
    elif RANGE_PRESETS.get(range, ("", 8))[1] is None:
        dates = [c.ref_date.date() for c in rows]
        s, e = (min(dates), max(dates)) if dates else (today, today)
    else:
        weeks = RANGE_PRESETS.get(range, RANGE_PRESETS["8w"])[1]
        range = range if range in RANGE_PRESETS else "8w"
        e = metrics.week_start(today) + timedelta(days=6)
        s = e - timedelta(weeks=weeks) + timedelta(days=1)
    period = metrics.Period(s, e)
    changes = metrics.in_period(rows, period)

    span = (e - s).days + 1
    prev = metrics.in_period(rows, metrics.Period(s - timedelta(days=span), s - timedelta(days=1)))
    summ, prev_summ = metrics.summary(changes, window), metrics.summary(prev, window)
    bd = metrics.breakdowns(changes, window)
    has_data = db.query(ChangeRequest.id).first() is not None
    return render(
        request, "dashboard.html",
        summary=summ, previous=prev_summ, bd=bd, bd_json=json.dumps(bd, ensure_ascii=False),
        notable=metrics.notable(changes, window)[:25], period=period, window=window, range=range,
        presets=RANGE_PRESETS, has_data=has_data, compare=range != "all",
        filters={"request_type": request_type, "department": department, "application": application},
        options={
            "request_type": _distinct(db, ChangeRequest.request_type),
            "department": _distinct(db, ChangeRequest.department),
            "application": _distinct(db, ChangeRequest.application),
        },
    )


# ---------- talepler ----------
@app.get("/changes", response_class=HTMLResponse)
def changes_list(request: Request, q: str = "", request_type: str = "", outcome: str = "", only: str = "",
                 db: Session = Depends(get_db)):
    window = settings_store.window(settings_store.get_all(db))
    query = db.query(ChangeRequest)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(ChangeRequest.jira_key.ilike(like), ChangeRequest.summary.ilike(like),
                                 ChangeRequest.application.ilike(like), ChangeRequest.microservices.ilike(like),
                                 ChangeRequest.requester.ilike(like), ChangeRequest.assignee.ilike(like)))
    if request_type:
        query = query.filter(ChangeRequest.request_type == request_type)
    if outcome:
        query = query.filter(ChangeRequest.outcome == outcome)
    if only == "open":
        query = query.filter(ChangeRequest.is_closed.is_(False))
    if only == "emergency":
        query = query.filter(ChangeRequest.is_emergency.is_(True))
    rows = sorted(query.all(), key=lambda c: c.ref_date, reverse=True)
    if only == "outside":
        rows = [c for c in rows if metrics.outside_window(c, window)]
    return render(request, "changes.html", rows=rows, q=q, request_type=request_type, outcome=outcome, only=only,
                  types=_distinct(db, ChangeRequest.request_type), window=window,
                  outside={c.id for c in rows if metrics.outside_window(c, window)})


FORM_FIELDS = ["summary", "request_type", "application", "microservices", "department", "requester", "assignee",
               "database", "db_type", "vendor", "vendor_ticket", "tag", "emergency_reason", "status"]


def _dt_input(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _bool_input(value: str) -> bool | None:
    return {"1": True, "0": False}.get(value)


def _apply_form(c: ChangeRequest, form: dict, full: bool) -> list[str]:
    errors = []
    c.outcome = form.get("outcome") if form.get("outcome") in OUTCOMES else "unknown"
    c.notes = (form.get("notes") or "").strip() or None
    if not full:
        return errors
    for f in FORM_FIELDS:
        setattr(c, f, (form.get(f) or "").strip() or None)
    c.summary = c.summary or ""
    c.request_type = c.request_type or "Diğer"
    c.status = c.status or ""
    c.jira_key = (form.get("jira_key") or "").strip() or None
    c.is_closed = form.get("is_closed") == "1"
    c.is_emergency = form.get("is_emergency") == "1"
    c.db_structural_change = _bool_input(form.get("db_structural_change", ""))
    c.pre_test_possible = _bool_input(form.get("pre_test_possible", ""))
    c.post_test_possible = _bool_input(form.get("post_test_possible", ""))
    c.created = _dt_input(form.get("created", "")) or c.created
    c.deploy_planned = _dt_input(form.get("deploy_planned", ""))
    c.resolved = _dt_input(form.get("resolved", ""))
    if not c.summary:
        errors.append("Özet zorunlu.")
    if not c.created:
        errors.append("Oluşturma tarihi zorunlu.")
    return errors


@app.get("/changes/new", response_class=HTMLResponse)
def change_new(request: Request, db: Session = Depends(get_db)):
    c = ChangeRequest(source="manual", created=datetime.now().replace(second=0, microsecond=0), outcome="unknown",
                      is_closed=False, is_emergency=False)
    return render(request, "change_form.html", c=c, editable=True, is_new=True,
                  types=_distinct(db, ChangeRequest.request_type))


@app.post("/changes/new")
async def change_create(request: Request, db: Session = Depends(get_db)):
    form = dict(await request.form())
    c = ChangeRequest(source="manual")
    errors = _apply_form(c, form, full=True)
    if c.jira_key and db.query(ChangeRequest).filter_by(jira_key=c.jira_key).first():
        errors.append(f"{c.jira_key} zaten kayıtlı.")
    if errors:
        return render(request, "change_form.html", c=c, editable=True, is_new=True, errors=errors,
                      types=_distinct(db, ChangeRequest.request_type))
    db.add(c)
    db.commit()
    flash(request, "Talep kaydedildi.")
    return back("/changes")


@app.get("/changes/{cid}", response_class=HTMLResponse)
def change_edit(request: Request, cid: int, db: Session = Depends(get_db)):
    c = db.get(ChangeRequest, cid)
    if not c:
        return back("/changes")
    window = settings_store.window(settings_store.get_all(db))
    return render(request, "change_form.html", c=c, editable=c.source == "manual", is_new=False,
                  types=_distinct(db, ChangeRequest.request_type), outside=metrics.outside_window(c, window),
                  lead=metrics.lead_hours(c), resolution=metrics.resolution_hours(c))


@app.post("/changes/{cid}")
async def change_update(request: Request, cid: int, db: Session = Depends(get_db)):
    c = db.get(ChangeRequest, cid)
    if not c:
        return back("/changes")
    errors = _apply_form(c, dict(await request.form()), full=c.source == "manual")
    if errors:
        db.rollback()
        return render(request, "change_form.html", c=c, editable=c.source == "manual", is_new=False, errors=errors,
                      types=_distinct(db, ChangeRequest.request_type))
    db.commit()
    flash(request, f"{c.jira_key or 'Talep'} güncellendi.")
    return back(f"/changes/{cid}")


@app.post("/changes/{cid}/delete")
def change_delete(request: Request, cid: int, db: Session = Depends(get_db)):
    c = db.get(ChangeRequest, cid)
    if c:
        db.delete(c)
        db.commit()
        flash(request, "Talep silindi.")
    return back("/changes")


# ---------- veri aktarımı ----------
@app.get("/import", response_class=HTMLResponse)
def import_page(request: Request, db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    logs = db.query(SyncLog).order_by(SyncLog.id.desc()).limit(20).all()
    return render(request, "import.html", logs=logs, values=values,
                  jira_ready=bool(values["jira.base_url"] and values["jira.pat"]),
                  total=db.query(ChangeRequest).count())


def _closed_statuses(values: dict[str, str]) -> set[str]:
    return {s.strip().casefold() for s in values["jira.closed_statuses"].split(",") if s.strip()}


@app.post("/import/csv")
async def import_csv(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    entry = SyncLog(kind="csv")
    try:
        ins, upd, skipped = importer.import_csv(db, content, _closed_statuses(settings_store.get_all(db)))
        entry.inserted, entry.updated = ins, upd
        entry.message = f"{file.filename}: {ins} yeni, {upd} güncellendi" + (f", {skipped} satır atlandı" if skipped else "")
        flash(request, entry.message)
    except Exception as exc:
        db.rollback()
        entry.ok, entry.message = False, f"{file.filename}: {exc}"
        flash(request, entry.message, "error")
    db.add(entry)
    db.commit()
    return back("/import")


@app.post("/import/jira")
def import_jira(request: Request, jql: str = Form(""), db: Session = Depends(get_db)):
    result = jira_client.sync(db, jql.strip() or None)
    flash(request, f"Jira: {result.inserted} yeni, {result.updated} güncellendi. {result.message}" if result.ok
          else f"Jira senkronu başarısız: {result.message}", "ok" if result.ok else "error")
    return back("/import")


# ---------- rapor ----------
def _report_week(week: str) -> date:
    d = _parse_date(week)
    return metrics.week_start(d or (date.today() - timedelta(days=7)))


@app.get("/report", response_class=HTMLResponse)
def report_page(request: Request, week: str = "", db: Session = Depends(get_db)):
    w = _report_week(week)
    data = report.build(db, w)
    values = settings_store.get_all(db)
    return render(request, "report.html", r=data, standalone=False, prev_week=(w - timedelta(days=7)).isoformat(),
                  next_week=(w + timedelta(days=7)).isoformat(), mail_ready=mailer.is_configured(values),
                  recipients=values["smtp.to"])


def _report_html(request: Request | None, data: dict) -> str:
    return templates.get_template("report_doc.html").render(r=data, standalone=True, generated=datetime.now())


@app.get("/report/download.html")
def report_download_html(request: Request, week: str = "", db: Session = Depends(get_db)):
    data = report.build(db, _report_week(week))
    name = f"vdeploy-haftalik-rapor-{data['week']:%Y-%m-%d}.html"
    return Response(_report_html(request, data), media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/report/download.csv")
def report_download_csv(week: str = "", db: Session = Depends(get_db)):
    data = report.build(db, _report_week(week))
    name = f"vdeploy-talepler-{data['week']:%Y-%m-%d}.csv"
    return Response(report.to_csv(data["changes"], data["window"]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def render_report_email(db: Session, week: date, values: dict[str, str]) -> list[str]:
    data = report.build(db, week)
    html = templates.get_template("report_doc.html").render(r=data, standalone=True, generated=datetime.now())
    p = data["period"]
    subject = f"Haftalık Deployment Raporu – {p.start:%d.%m.%Y}–{p.end:%d.%m.%Y}"
    entry = SyncLog(kind="mail")
    try:
        recipients = mailer.send(values, subject, html, attachments=[
            (f"talepler-{p.start:%Y-%m-%d}.csv", report.to_csv(data["changes"], data["window"]), "text/csv")])
        entry.message = f"Rapor gönderildi: {', '.join(recipients)}"
        return recipients
    except Exception as exc:
        entry.ok, entry.message = False, f"Rapor gönderilemedi: {exc}"
        raise
    finally:
        db.add(entry)
        db.commit()


@app.post("/report/send")
def report_send(request: Request, week: str = Form(""), db: Session = Depends(get_db)):
    w = _report_week(week)
    try:
        recipients = render_report_email(db, w, settings_store.get_all(db))
        flash(request, f"Rapor gönderildi: {', '.join(recipients)}")
    except Exception as exc:
        flash(request, f"Rapor gönderilemedi: {exc}", "error")
    return back(f"/report?week={w.isoformat()}")


# ---------- ayarlar ----------
SECTIONS = {
    "smtp": ["smtp.host", "smtp.port", "smtp.security", "smtp.user", "smtp.password", "smtp.from", "smtp.to"],
    "jira": ["jira.base_url", "jira.pat", "jira.jql", "jira.verify_ssl", "jira.closed_statuses"],
    "window": ["window.days", "window.start", "window.end"],
    "schedule": ["schedule.day", "schedule.time", "jira.auto_sync", "smtp.auto_send"],
    "ad": ["ad.enabled", "ad.server", "ad.port", "ad.use_ssl", "ad.domain", "ad.base_dn", "ad.allowed_group"],
}
CHECKBOXES = {"jira.verify_ssl", "jira.auto_sync", "smtp.auto_send", "ad.enabled", "ad.use_ssl"}


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tab: str = "smtp", db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    return render(request, "settings.html", tab=tab if tab in SECTIONS else "smtp", v=values,
                  has_secret={k: bool(values[k]) for k in settings_store.SECRET_KEYS},
                  window=settings_store.window(values), next_run=scheduler.next_run(),
                  scheduler_on=config.SCHEDULER_ENABLED)


@app.post("/settings/{section}")
async def settings_save(request: Request, section: str, db: Session = Depends(get_db)):
    if section not in SECTIONS:
        return back("/settings")
    form = await request.form()
    new: dict[str, str] = {}
    for key in SECTIONS[section]:
        if key in CHECKBOXES:
            new[key] = "1" if form.get(key) else "0"
        elif key == "window.days":
            new[key] = ",".join(form.getlist(key))
        else:
            new[key] = str(form.get(key, "")).strip()
    if section == "ad" and new["ad.enabled"] == "1" and not new["ad.server"]:
        flash(request, "AD girişini açmak için sunucu adresi gerekli.", "error")
        return back(f"/settings?tab={section}")
    settings_store.set_many(db, new)
    if section == "schedule":
        scheduler.reschedule(settings_store.get_all(db))
    flash(request, "Ayarlar kaydedildi.")
    return back(f"/settings?tab={section}")


@app.post("/settings/smtp/test")
def settings_smtp_test(request: Request, to: str = Form(""), db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    try:
        recipients = mailer.send(values, "vDeploy test e-postası",
                                 "<p>vDeploy SMTP ayarları çalışıyor.</p>",
                                 to=[x.strip() for x in to.split(",") if x.strip()] or None)
        flash(request, f"Test e-postası gönderildi: {', '.join(recipients)}")
    except Exception as exc:
        flash(request, f"Test e-postası gönderilemedi: {exc}", "error")
    return back("/settings?tab=smtp")


@app.post("/settings/jira/test")
def settings_jira_test(request: Request, db: Session = Depends(get_db)):
    try:
        me = jira_client.client_from_settings(settings_store.get_all(db)).myself()
        flash(request, f"Jira bağlantısı başarılı: {me.get('displayName') or me.get('name')}")
    except Exception as exc:
        flash(request, f"Jira bağlantısı başarısız: {exc}", "error")
    return back("/settings?tab=jira")


@app.post("/settings/ad/test")
def settings_ad_test(request: Request, username: str = Form(""), password: str = Form(""),
                     db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    values["ad.enabled"] = "1"
    result = auth.test_connection(values, username, password)
    flash(request, f"AD doğrulaması başarılı: {result.display_name}" if result.ok
          else f"AD doğrulaması başarısız: {result.error}", "ok" if result.ok else "error")
    return back("/settings?tab=ad")
