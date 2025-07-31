import pandas as pd
from pathlib import Path


def summarize_table(file_path: str, max_rows: int = 5) -> str:
    """Return a Markdown preview of an Excel or CSV table."""
    path = Path(file_path)
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path)
        return df.head(max_rows).to_markdown(index=False)
    elif path.suffix.lower() in ['.xls', '.xlsx']:
        xls = pd.ExcelFile(path)
        parts = []
        for sheet in xls.sheet_names:
            df = xls.parse(sheet).head(max_rows)
            parts.append(f"### {sheet}")
            parts.append(df.to_markdown(index=False))
        return "\n\n".join(parts)
    else:
        raise ValueError('Unsupported file type: %s' % path.suffix)


def answer_question_with_pandas(question: str, file_path: str) -> str:
    """Stub that would delegate reasoning to the LLM using pandas."""
    summary = summarize_table(file_path)
    prompt = (
        f"Table preview:\n{summary}\n\n"
        f"Question: {question}\n"
        "Write pandas code to answer the question."
    )
    # Here you would pass `prompt` to the LLM and execute the produced code.
    # This is left as a placeholder.
    return prompt
