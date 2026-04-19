"""FastAPI アプリケーション。SSE でリアルタイム進捗をブラウザに送る。"""

import asyncio
import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from google.analytics.admin import AnalyticsAdminServiceClient
from google.oauth2.credentials import Credentials as GoogleCredentials

from src.adapters.csv_adapter import CSVAdapter
from src.adapters.drive_adapter import find_folder_by_name, get_recent_docs_text, list_folders
from src.adapters.ga4_adapter import GA4Adapter
from src.auth.google_oauth import (
    build_auth_url,
    exchange_code,
    refresh_access_token,
)
from src.auth.session_store import (
    create_session,
    delete_session,
    get_session,
    save_state,
    update_access_token,
    verify_and_consume_state,
)
from src.llm.anthropic_client import AnthropicClient
from src.orchestrator.hypothesis_generator import Hypothesis, HypothesisGenerator
from src.orchestrator.report_generator import ReportGenerator
from src.orchestrator.request_parser import ParsedRequest, RequestParser
from src.storage.duckdb_client import DuckDBClient
from src.orchestrator.marketing_agent import generate_marketing_insight
from src.orchestrator.prompt_reviewer import PromptReviewer
from src.storage.correction_store import format_corrections_context, get_recent_corrections, save_correction
from src.storage.eval_store import compute_and_save as eval_compute_and_save
from src.storage.memory_store import format_past_context, get_recent_memories, save_memory
from src.storage.prompt_store import PROMPT_FILES, save_prompt_version
from src.storage.sql_validator import SQLValidationError, validate_and_sanitize

load_dotenv()

app = FastAPI(title="AutoAnalytics")

_executor = ThreadPoolExecutor(max_workers=4)

PROMPTS_DIR = Path("prompts")
DATA_DIR = Path("data")
REPORTS_DIR = Path("reports")

DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _data_context(db: DuckDBClient, table: str) -> str:
    try:
        return db.get_data_context(table)
    except Exception as e:
        return f"データコンテキスト取得失敗: {e}"


def _fmt_result(rows: list[dict], max_rows: int = 10) -> str:
    if not rows:
        return "（結果なし）"
    headers = list(rows[0].keys())
    lines = [" | ".join(headers), "-" * 40]
    for row in rows[:max_rows]:
        lines.append(" | ".join(str(v) for v in row.values()))
    if len(rows) > max_rows:
        lines.append(f"... 他 {len(rows) - max_rows:,} 行")
    return "\n".join(lines)


# ------------------------------------------------------------------
# 同期分析ランナー（スレッド内で実行）
# ------------------------------------------------------------------

def _run_shared_steps(
    db: DuckDBClient,
    request_text: str,
    source_id: str,
    emit: callable,
    email: str = "",
) -> None:
    """Step 2〜5: 依頼パース → 仮説検証 → レポート → マーケティング提案。
    CSV・GA4 両フローで共有する。
    """
    system_prompt = _load_prompt("system_prompt.md")
    hypothesis_prompt = _load_prompt("hypothesis_prompt.md")
    report_prompt = _load_prompt("report_prompt.md")
    llm = AnthropicClient()

    # Step 2: 依頼パース
    emit({"step": 2, "status": "running", "message": "分析依頼を解析中..."})
    parsed: ParsedRequest = RequestParser(llm, system_prompt).parse(
        request_text, db.list_tables()
    )
    emit({
        "step": 2, "status": "done", "message": parsed.summary,
        "detail": {"kpi": parsed.kpi, "period": parsed.period, "dimensions": parsed.dimensions},
    })

    # Step 3: 仮説生成 & SQL 実行
    emit({"step": 3, "status": "running", "message": "仮説を生成中..."})
    context = _data_context(db, parsed.target_table)
    past_context = format_past_context(
        get_recent_memories(email, source_id) if email else []
    )
    corrections_context = format_corrections_context(
        get_recent_corrections(email, source_id) if email else []
    )
    hypotheses: list[Hypothesis] = HypothesisGenerator(
        llm, system_prompt, hypothesis_prompt
    ).generate(parsed, context, past_context, corrections_context)

    allowed_tables = db.list_tables()
    for h in hypotheses:
        emit({"step": 3, "status": "running", "message": f"仮説 {h.index} を検証中: {h.title[:40]}..."})
        if not h.sql:
            h.result, h.status = "（SQL なし）", "no_sql"
            continue
        try:
            rows = db.query(validate_and_sanitize(h.sql, allowed_tables))
            h.result = _fmt_result(rows) if rows else "（該当データなし）"
            h.status = "supported" if rows else "no_data"
        except SQLValidationError as e:
            h.result, h.status = f"SQL バリデーションエラー: {e}", "error"
            if email:
                try:
                    save_correction(email, source_id, "sql_validation", h.sql[:300], str(e))
                except Exception:
                    pass
        except Exception as e:
            h.result, h.status = f"SQL 実行エラー: {e}", "error"
            if email:
                try:
                    save_correction(email, source_id, "sql_execution", h.sql[:300], str(e))
                except Exception:
                    pass

    emit({"step": 3, "status": "done", "message": f"{len(hypotheses)} つの仮説を検証完了"})

    # Step 4: レポート生成
    emit({"step": 4, "status": "running", "message": "レポートを生成中..."})
    rep_gen = ReportGenerator(llm, system_prompt, report_prompt)
    report = rep_gen.generate(parsed, hypotheses)
    output_path = rep_gen.save(report, str(REPORTS_DIR))

    if email:
        findings, actions = ReportGenerator.extract_summary_and_actions(report)
        try:
            save_memory(email, source_id, parsed.kpi, parsed.summary, findings, actions)
        except Exception:
            pass
        eval_compute_and_save(email, source_id, hypotheses, report)

    emit({"step": 4, "status": "done", "message": "レポート生成完了"})
    emit({"type": "report", "content": report, "filename": output_path.name})



def _fetch_drive_context(access_token: str, folder_id: str, emit: callable) -> str:
    """Drive フォルダから最新議事録を取得してコンテキスト文字列を返す。失敗時は空文字列。"""
    if not access_token or not folder_id:
        return ""
    try:
        emit({"type": "drive_status", "message": "Drive から資料を取得中..."})
        text = get_recent_docs_text(access_token, folder_id)
        if text:
            emit({"type": "drive_status", "message": "Drive 資料を取得しました"})
            return f"[クライアント資料（直近の議事録）]\n{text}\n\n"
    except Exception:
        pass
    return ""


def _run_analysis(
    csv_path: str,
    request_text: str,
    table_name: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    email: str = "",
    access_token: str = "",
    drive_folder_id: str = "",
) -> None:
    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    db_path = str(DATA_DIR / f"session_{uuid.uuid4().hex}.duckdb")
    try:
        with DuckDBClient(db_path) as db:
            emit({"step": 1, "status": "running", "message": "CSV を読み込み中..."})
            meta = CSVAdapter(db).load(csv_path, table_name)
            emit({"step": 1, "status": "done", "message": meta.summary()})

            client_context = _fetch_drive_context(access_token, drive_folder_id, emit)
            augmented = f"{client_context}{request_text}" if client_context else request_text
            _run_shared_steps(db, augmented, "csv", emit, email)
    except Exception as e:
        emit({"type": "error", "message": str(e)})
    finally:
        emit({"type": "end"})
        Path(db_path).unlink(missing_ok=True)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.get("/")
async def index() -> FileResponse:
    return FileResponse(
        "static/index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/drive/folders")
async def drive_folders(session_id: str = Cookie(default="")) -> list[dict]:
    """ログインユーザーがアクセスできる Drive フォルダ一覧を返す。"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    access_token = session.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="アクセストークンがありません")
    try:
        return list_folders(access_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze(
    csv_file: UploadFile = File(...),
    request_text: str = Form(...),
    table_name: str = Form("main_data"),
    drive_folder_id: str = Form(default=""),
    session_id: str = Cookie(default=""),
) -> StreamingResponse:
    # CSV を一時ファイルに保存
    suffix = Path(csv_file.filename or "data.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await csv_file.read())
        tmp_path = tmp.name

    session = get_session(session_id)
    email = session.get("email", "") if session else ""
    access_token = session.get("access_token", "") if session else ""

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    loop.run_in_executor(
        _executor, _run_analysis,
        tmp_path, request_text, table_name, queue, loop, email, access_token, drive_folder_id,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            deadline = asyncio.get_running_loop().time() + 180.0
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト（180秒）'}, ensure_ascii=False)}\n\n"
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=min(15.0, remaining))
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") in ("end", "error"):
                        break
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------
# Auth routes
# ------------------------------------------------------------------

@app.get("/auth/login")
async def auth_login() -> RedirectResponse:
    url, state = build_auth_url()
    save_state(state)  # Supabase に保存（マルチインスタンス対応）
    return RedirectResponse(url)


@app.get("/auth/callback")
async def auth_callback(
    code: str,
    state: str,
) -> RedirectResponse:
    if not verify_and_consume_state(state):
        raise HTTPException(status_code=400, detail="Invalid state")
    user_data = await exchange_code(code)
    session_id = create_session(user_data)
    response = RedirectResponse("/")
    response.set_cookie("session_id", session_id, httponly=True, max_age=3600 * 8)
    return response


@app.get("/auth/me")
async def auth_me(session_id: str = Cookie(default="")) -> JSONResponse:
    session = get_session(session_id)
    if not session:
        return JSONResponse({"authenticated": False})
    return JSONResponse({
        "authenticated": True,
        "email": session.get("email"),
        "name": session.get("name"),
        "picture": session.get("picture"),
    })


@app.post("/auth/logout")
async def auth_logout(session_id: str = Cookie(default="")) -> JSONResponse:
    delete_session(session_id)
    response = JSONResponse({"ok": True})
    response.delete_cookie("session_id")
    return response


# ------------------------------------------------------------------
# GA4 analyze route
# ------------------------------------------------------------------

def _run_ga4_analysis(
    property_id: str,
    start_date: str,
    end_date: str,
    request_text: str,
    access_token: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    email: str = "",
    refresh_token: str = "",
    session_id: str = "",
) -> None:
    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    db_path = str(DATA_DIR / f"session_{uuid.uuid4().hex}.duckdb")
    try:
        with DuckDBClient(db_path) as db:
            # Step 1: GA4 データ取得（トークンリフレッシュ対応）
            emit({"step": 1, "status": "running", "message": "GA4 からデータを取得中..."})
            try:
                meta = GA4Adapter(db, access_token).load(property_id, start_date, end_date)
            except Exception:
                if not refresh_token:
                    raise
                access_token = refresh_access_token(refresh_token)
                if session_id:
                    update_access_token(session_id, access_token)
                meta = GA4Adapter(db, access_token).load(property_id, start_date, end_date)
            emit({"step": 1, "status": "done", "message": meta.summary()})

            # Drive: property_id と同名フォルダを自動検索
            drive_folder_id = ""
            try:
                drive_folder_id = find_folder_by_name(access_token, property_id) or ""
            except Exception:
                pass
            client_context = _fetch_drive_context(access_token, drive_folder_id, emit)

            augmented_request = (
                f"[重要: 取得データは {start_date} 〜 {end_date} の期間のみ存在する。"
                f"SQL の WHERE 句およびレポートの期間記述はこの範囲を厳守すること。"
                f"この範囲外（前年同期など）のデータは存在しないため、前年比較の仮説は絶対に立てないこと。]\n"
                f"{client_context}"
                f"{request_text}"
            )
            _run_shared_steps(db, augmented_request, property_id, emit, email)
    except Exception as e:
        emit({"type": "error", "message": str(e)})
    finally:
        emit({"type": "end"})
        Path(db_path).unlink(missing_ok=True)


def _fetch_ga4_properties(access_token: str) -> list[dict]:
    creds = GoogleCredentials(token=access_token)
    client = AnalyticsAdminServiceClient(credentials=creds)
    properties = []
    for summary in client.list_account_summaries():
        for prop in summary.property_summaries:
            prop_id = prop.property.split("/")[-1]
            properties.append({
                "id": prop_id,
                "name": prop.display_name,
                "account": summary.display_name,
            })
    return properties


@app.get("/api/ga4/properties")
async def list_ga4_properties(session_id: str = Cookie(default="")) -> list[dict]:
    """ログインユーザーがアクセスできるGA4プロパティ一覧を返す。"""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    access_token = session.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="アクセストークンがありません")
    try:
        return _fetch_ga4_properties(access_token)
    except Exception:
        # トークン期限切れの場合はリフレッシュして再試行
        rt = session.get("refresh_token")
        if not rt:
            raise HTTPException(status_code=401, detail="セッションが期限切れです。再ログインしてください。")
        try:
            new_token = refresh_access_token(rt)
            update_access_token(session_id, new_token)
            return _fetch_ga4_properties(new_token)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/ga4")
async def analyze_ga4(
    property_id: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    request_text: str = Form(...),
    session_id: str = Cookie(default=""),
) -> StreamingResponse:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="ログインが必要です")

    access_token = session.get("access_token")
    if not access_token:
        raise HTTPException(status_code=401, detail="アクセストークンがありません")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    email = session.get("email", "")
    refresh_token = session.get("refresh_token", "")
    loop.run_in_executor(
        _executor, _run_ga4_analysis,
        property_id, start_date, end_date, request_text, access_token, queue, loop, email,
        refresh_token, session_id,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        deadline = asyncio.get_running_loop().time() + 180.0
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト'}, ensure_ascii=False)}\n\n"
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=min(15.0, remaining))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("end", "error"):
                    break
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run_prompt_review(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    try:
        report_files = sorted(REPORTS_DIR.glob("*.md"), reverse=True)[:3]
        report_texts = [r.read_text(encoding="utf-8") for r in report_files]

        if not report_texts:
            emit({"type": "error", "message": "reports/ にレポートがありません。先に分析を実行してください。"})
            return

        emit({"type": "progress", "message": f"{len(report_texts)} 件のレポートを読み込みました"})

        reviewer = PromptReviewer()
        emit({"type": "progress", "message": "Reviewer: レポートを審査中..."})
        feedback = reviewer.review(report_texts)

        emit({"type": "feedback", "content": feedback.raw})

        if feedback.is_empty:
            emit({"type": "done", "message": "品質上の問題は検出されませんでした", "updated": []})
            return

        updated = []
        for name, filepath in PROMPT_FILES.items():
            emit({"type": "progress", "message": f"PromptEngineer: {name} を改善中..."})
            path = Path(filepath)
            if not path.exists():
                emit({"type": "progress", "message": f"{name}: ファイルが見つかりません"})
                continue
            current = path.read_text(encoding="utf-8")
            improved = reviewer.improve_prompt(name, current, feedback)
            save_prompt_version(name, improved, review_feedback=feedback.raw)
            updated.append(name)
            emit({"type": "progress", "message": f"✓ {name} を更新しました"})

        emit({"type": "done", "message": "プロンプト改善が完了しました", "updated": updated})

    except Exception as e:
        emit({"type": "error", "message": str(e)})
    finally:
        emit({"type": "end"})


@app.post("/api/review-prompt")
async def review_prompt_api(session_id: str = Cookie(default="")) -> StreamingResponse:
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="ログインが必要です")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    loop.run_in_executor(_executor, _run_prompt_review, queue, loop)

    async def event_stream() -> AsyncGenerator[str, None]:
        deadline = asyncio.get_running_loop().time() + 300.0  # 5分タイムアウト
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト'}, ensure_ascii=False)}\n\n"
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=min(15.0, remaining))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("end", "error"):
                    break
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run_marketing_insight(
    report_text: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)
    try:
        content = generate_marketing_insight(report_text)
        emit({"type": "marketing", "content": content})
    except Exception as e:
        emit({"type": "error", "message": str(e)})
    finally:
        emit({"type": "end"})


@app.post("/api/marketing-insight")
async def marketing_insight_api(filename: str = Form(...)) -> StreamingResponse:
    path = REPORTS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="レポートが見つかりません")
    report_text = path.read_text(encoding="utf-8")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    loop.run_in_executor(_executor, _run_marketing_insight, report_text, queue, loop)

    async def event_stream() -> AsyncGenerator[str, None]:
        deadline = asyncio.get_running_loop().time() + 120.0
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト'}, ensure_ascii=False)}\n\n"
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=min(15.0, remaining))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("end", "error"):
                    break
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/reports")
async def list_reports() -> list[dict]:
    reports = sorted(REPORTS_DIR.glob("report_*.md"), reverse=True)
    return [{"filename": r.name, "size": r.stat().st_size} for r in reports[:20]]


@app.get("/api/reports/{filename}")
async def download_report(filename: str) -> FileResponse:
    path = REPORTS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="レポートが見つかりません")
    return FileResponse(path, media_type="text/markdown", filename=filename)


# Static files（最後にマウント: / より後で定義しないとルートが上書きされる）
app.mount("/static", StaticFiles(directory="static"), name="static")
