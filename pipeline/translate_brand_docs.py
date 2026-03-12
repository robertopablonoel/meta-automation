#!/usr/bin/env python3
"""One-time script: translate English brand PDFs to Spanish via Claude API.

Extracts text from the 3 English brand PDFs and translates each to
Latin American Spanish, saving results as plain text files in brand/es/.

Usage:
    venv/bin/python -m pipeline.translate_brand_docs
"""

import sys
from pathlib import Path

import anthropic
import pdfplumber

from .config import (
    ANTHROPIC_API_KEY,
    AVATAR_SHEET_PDF,
    OFFER_BRIEF_PDF,
    NECESSARY_BELIEFS_PDF,
    BRAND_DIR_ES,
    AVATAR_SHEET_ES,
    OFFER_BRIEF_ES,
    NECESSARY_BELIEFS_ES,
    MODEL_NAME,
)


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF."""
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def translate_text(client: anthropic.Anthropic, text: str, doc_name: str, max_retries: int = 5) -> str:
    """Translate a brand document to Latin American Spanish via Claude."""
    import time
    print(f"  Translating {doc_name} ({len(text):,} chars)...")

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=8192,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Translate the following brand document to Latin American Spanish.\n\n"
                        f"Rules:\n"
                        f"- Preserve ALL formatting, structure, headers, and bullet points exactly\n"
                        f"- Keep marketing terminology natural in Spanish (not literal translations)\n"
                        f"- Use 'tú' form (informal), not 'usted'\n"
                        f"- Keep brand name 'Spicy Cubes Dailies' untranslated\n"
                        f"- Keep ingredient names in their common Spanish forms where they exist\n"
                        f"- Do NOT add any commentary — output ONLY the translated text\n\n"
                        f"---\n\n"
                        f"{text}"
                    ),
                }],
            )
            translated = response.content[0].text
            print(f"  Done ({len(translated):,} chars)")
            return translated
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as e:
            delay = 2 * (2 ** attempt)
            print(f"  Retry {attempt + 1}/{max_retries} after {type(e).__name__}, waiting {delay}s...")
            time.sleep(delay)

    raise RuntimeError(f"Failed to translate {doc_name} after {max_retries} retries")


def main():
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set. Add it to .env and try again.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=120.0)

    # Create output directory
    BRAND_DIR_ES.mkdir(parents=True, exist_ok=True)

    docs = [
        (AVATAR_SHEET_PDF, AVATAR_SHEET_ES, "Avatar Sheet"),
        (OFFER_BRIEF_PDF, OFFER_BRIEF_ES, "Offer Brief"),
        (NECESSARY_BELIEFS_PDF, NECESSARY_BELIEFS_ES, "Necessary Beliefs"),
    ]

    for pdf_path, output_path, name in docs:
        if output_path.exists():
            print(f"  Skipping {name} — {output_path} already exists")
            continue

        if not pdf_path.exists():
            print(f"  Warning: {pdf_path} not found, skipping {name}")
            continue

        english_text = extract_pdf_text(pdf_path)
        spanish_text = translate_text(client, english_text, name)

        output_path.write_text(spanish_text, encoding="utf-8")
        print(f"  Saved -> {output_path}")

    print(f"\nDone. Spanish brand docs saved to {BRAND_DIR_ES}/")


if __name__ == "__main__":
    main()
