"""FastAPI アプリケーション。SSE でリアルタイム進捗をブラウザに送る。"""

import asyncio
import json
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.adapters.csv_adapter import CSVAdapter
from src.llm.anthropic_client import AnthropicClient
from src.orchestrator.hypothesis_generator import Hypothesis, HypothesisGenerator
from src.orchestrator.report_generator import ReportGenerator
from src.orchestrator.request_parser import ParsedRequest, RequestParser
from src.storage.duckdb_client import DuckDBClient
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

def _run_analysis(
    csv_path: str,
    request_text: str,
    table_name: str,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    def emit(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)

    db_path = str(DATA_DIR / f"session_{uuid.uuid4().hex}.duckdb")

    try:
        system_prompt = _load_prompt("system_prompt.md")
        hypothesis_prompt = _load_prompt("hypothesis_prompt.md")
        report_prompt = _load_prompt("report_prompt.md")
        llm = AnthropicClient()

        with DuckDBClient(db_path) as db:

            # Step 1: CSV ロード
            emit({"step": 1, "status": "running", "message": "CSV を読み込み中..."})
            meta = CSVAdapter(db).load(csv_path, table_name)
            emit({"step": 1, "status": "done", "message": meta.summary()})

            # Step 2: 依頼パース
            emit({"step": 2, "status": "running", "message": "分析依頼を解析中..."})
            parsed: ParsedRequest = RequestParser(llm, system_prompt).parse(
                request_text, db.list_tables()
            )
            emit({
                "step": 2,
                "status": "done",
                "message": parsed.summary,
                "detail": {
                    "kpi": parsed.kpi,
                    "period": parsed.period,
                    "dimensions": parsed.dimensions,
                },
            })

            # Step 3: 仮説生成 & SQL 実行
            emit({"step": 3, "status": "running", "message": "仮説を生成中..."})
            context = _data_context(db, parsed.target_table)
            hypotheses: list[Hypothesis] = HypothesisGenerator(
                llm, system_prompt, hypothesis_prompt
            ).generate(parsed, context)

            allowed_tables = db.list_tables()
            for h in hypotheses:
                emit({"step": 3, "status": "running", "message": f"仮説 {h.index} を検証中: {h.title[:40]}..."})
                if not h.sql:
                    h.result = "（SQL なし）"
                    h.status = "no_sql"
                    continue
                try:
                    safe_sql = validate_and_sanitize(h.sql, allowed_tables)
                    rows = db.query(safe_sql)
                    if rows:
                        h.result = _fmt_result(rows)
                        h.status = "supported"
                    else:
                        h.result = "（該当データなし）"
                        h.status = "no_data"
                except SQLValidationError as e:
                    h.result = f"SQL バリデーションエラー: {e}"
                    h.status = "error"
                except Exception as e:
                    h.result = f"SQL 実行エラー: {e}"
                    h.status = "error"

            emit({"step": 3, "status": "done", "message": f"{len(hypotheses)} つの仮説を検証完了"})

            # Step 4: レポート生成
            emit({"step": 4, "status": "running", "message": "レポートを生成中..."})
            rep_gen = ReportGenerator(llm, system_prompt, report_prompt)
            report = rep_gen.generate(parsed, hypotheses)
            output_path = rep_gen.save(report, str(REPORTS_DIR))
            emit({"step": 4, "status": "done", "message": "レポート生成完了"})

            emit({"type": "report", "content": report, "filename": output_path.name})

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
    return FileResponse("static/index.html")


@app.post("/api/analyze")
async def analyze(
    csv_file: UploadFile = File(...),
    request_text: str = Form(...),
    table_name: str = Form("main_data"),
) -> StreamingResponse:
    # CSV を一時ファイルに保存
    suffix = Path(csv_file.filename or "data.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await csv_file.read())
        tmp_path = tmp.name

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    loop.run_in_executor(
        _executor, _run_analysis, tmp_path, request_text, table_name, queue, loop
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=180.0)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") in ("end", "error"):
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト（180秒）'}, ensure_ascii=False)}\n\n"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

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
