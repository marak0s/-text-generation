"""Utilities for summarizing tables and running pandas analysis."""

import pandas as pd
from pathlib import Path

__all__ = [
    "summarize_table",
    "answer_question_with_pandas",
    "execute_pandas_code",
]


def summarize_table(file_path: str, max_rows: int = 5) -> str:
    """Return a lightweight textual preview of an Excel or CSV table."""
    path = Path(file_path)
    parts = [f"Table: {path.name}"]

    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path, nrows=max_rows)
        columns = ', '.join(df.columns.astype(str))
        parts.append(f"Columns: {columns}")
        parts.append(df.to_csv(index=False))
        return "\n".join(parts)

    if path.suffix.lower() in {'.xls', '.xlsx'}:
        xls = pd.ExcelFile(path)
        for sheet in xls.sheet_names:
            df = xls.parse(sheet, nrows=max_rows)
            columns = ', '.join(df.columns.astype(str))
            parts.append(f"Sheet: {sheet}")
            parts.append(f"Columns: {columns}")
            parts.append(df.to_csv(index=False))
        return "\n".join(parts)

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


def execute_pandas_code(code: str, file_path: str) -> str:
    """Execute pandas code against the provided table and return the result."""
    path = Path(file_path)
    local_vars = {}

    try:
        if path.suffix.lower() == '.csv':
            local_vars['df'] = pd.read_csv(path)
        elif path.suffix.lower() in {'.xls', '.xlsx'}:
            xls = pd.ExcelFile(path)
            for sheet in xls.sheet_names:
                local_vars[sheet] = xls.parse(sheet)
        else:
            return f'Unsupported file type: {path.suffix}'

        exec(code, {'pd': pd}, local_vars)
        result = local_vars.get('result')
        if isinstance(result, pd.DataFrame):
            return result.head().to_csv(index=False)
        return str(result) if result is not None else 'No result'
    except Exception as e:
        return f'Error executing code: {e}'
