"""書籍PDFをRAG用にSupabaseへ取り込む。

使い方:
    python -m src.tools.ingest_book docs/chapter_01.pdf
    python -m src.tools.ingest_book docs/  # フォルダ内の未処理PDFをすべて処理

処理フロー:
    PDF → ページごとにPNG化 → Claude Vision OCR → チャンク分割
    → OpenAI Embedding → Supabase marketing_docs へ保存
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import fitz  # PyMuPDF
import httpx
from dotenv import load_dotenv

load_dotenv()

import anthropic
from openai import OpenAI

# --- 設定 ---
CHUNK_SIZE = 800
CHUNK_OVERLAP = 160
EMBED_MODEL = "text-embedding-3-small"
OCR_MODEL = "claude-haiku-4-5-20251001"

_anthropic = anthropic.Anthropic()
_openai = OpenAI()

# Supabase REST API クライアント（httpx直接）
_SUPABASE_URL = os.environ["SUPABASE_URL"]
_SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
_HEADERS = {
    "apikey": _SUPABASE_KEY,
    "Authorization": f"Bearer {_SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def _supabase_select(table: str, filters: dict) -> list:
    params = {k: f"eq.{v}" for k, v in filters.items()}
    params["select"] = "id"
    params["limit"] = "1"
    res = httpx.get(f"{_SUPABASE_URL}/rest/v1/{table}", headers=_HEADERS, params=params)
    res.raise_for_status()
    return res.json()


def _supabase_insert(table: str, rows: list) -> None:
    res = httpx.post(
        f"{_SUPABASE_URL}/rest/v1/{table}",
        headers=_HEADERS,
        content=json.dumps(rows),
    )
    res.raise_for_status()


# ---------------------------------------------------------------------------
# 既処理ファイルの確認
# ---------------------------------------------------------------------------

def _already_processed(source_file: str) -> bool:
    rows = _supabase_select("marketing_docs", {"source_file": source_file})
    return bool(rows)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _ocr_page(page: fitz.Page) -> str:
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    image_data = base64.b64encode(pix.tobytes("png")).decode()

    response = _anthropic.messages.create(
        model=OCR_MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": image_data},
                },
                {
                    "type": "text",
                    "text": (
                        "この画像に書かれているテキストをすべて正確に抽出してください。"
                        "目次・ページ番号のみのページは「（目次）」または「（ページ番号のみ）」とだけ出力してください。"
                        "レイアウトは気にせず、読める文字をすべて出力してください。"
                    ),
                },
            ],
        }],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# チャンク分割
# ---------------------------------------------------------------------------

def _split_chunks(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if len(c.strip()) > 20]


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def _embed(texts: list[str]) -> list[list[float]]:
    response = _openai.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def ingest_pdf(pdf_path: Path) -> None:
    source_file = pdf_path.name

    if _already_processed(source_file):
        print(f"[SKIP] {source_file} は取り込み済みです")
        return

    print(f"[START] {source_file} を処理します")
    doc = fitz.open(str(pdf_path))
    total = len(doc)

    for page_num in range(total):
        print(f"  ページ {page_num + 1}/{total} OCR中...", end=" ", flush=True)
        text = _ocr_page(doc[page_num])

        if text in ("（目次）", "（ページ番号のみ）") or len(text) < 30:
            print("スキップ")
            continue

        chunks = _split_chunks(text)
        if not chunks:
            print("スキップ（テキストなし）")
            continue

        embeddings = _embed(chunks)
        rows = [
            {
                "source_file": source_file,
                "page_num": page_num + 1,
                "chunk_index": i,
                "content": chunk,
                "embedding": embedding,
            }
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        _supabase_insert("marketing_docs", rows)
        print(f"{len(chunks)}チャンク保存")

    doc.close()
    print(f"[DONE] {source_file} 完了")


def main() -> None:
    parser = argparse.ArgumentParser(description="書籍PDFをSupabaseへ取り込む")
    parser.add_argument("path", help="PDFファイルまたはフォルダのパス")
    args = parser.parse_args()

    target = Path(args.path)
    if target.is_dir():
        pdfs = sorted(target.glob("*.pdf"))
        if not pdfs:
            print("PDFが見つかりません")
            sys.exit(1)
        for pdf in pdfs:
            ingest_pdf(pdf)
    elif target.is_file() and target.suffix.lower() == ".pdf":
        ingest_pdf(target)
    else:
        print(f"PDFファイルまたはフォルダを指定してください: {target}")
        sys.exit(1)


if __name__ == "__main__":
    main()
