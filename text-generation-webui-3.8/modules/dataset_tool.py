import pandas as pd
from pathlib import Path

try:
    import polars as pl
except Exception:  # pragma: no cover - optional dependency
    pl = None

_loaded_tables: dict[str, str] = {}


def register_table(file_path: str | Path) -> str:
    """Register a table path and return its name identifier."""
    path = Path(file_path)
    name = path.name
    _loaded_tables[name] = str(path)
    return name


def get_table_path(name: str) -> str | None:
    """Return the registered path for a table name if available."""
    return _loaded_tables.get(name)


def summarize_table(file_path: str, max_rows: int = 5) -> str:
    """Return a lightweight textual preview of an Excel, CSV or Parquet table."""
    path = Path(file_path)
    parts = [f"Table: {path.name}"]
    suffix = path.suffix.lower()

    if suffix == '.csv':
        if pl:
            df = pl.read_csv(path, n_rows=max_rows).to_pandas()
        else:
            df = pd.read_csv(path, nrows=max_rows)
        columns = ', '.join(df.columns.astype(str))
        parts.append(f"Columns: {columns}")
        parts.append(df.to_csv(index=False))
        parts.append(f"Use get_table_path('{path.name}') to load this table in Python.")
        return "\n".join(parts)

    if suffix in {'.xls', '.xlsx'}:
        xls = pd.ExcelFile(path)
        for sheet in xls.sheet_names:
            if pl:
                pdf = pl.read_excel(path, sheet_id=sheet, n_rows=max_rows).to_pandas()
            else:
                pdf = xls.parse(sheet, nrows=max_rows)
            columns = ', '.join(pdf.columns.astype(str))
            parts.append(f"Sheet: {sheet}")
            parts.append(f"Columns: {columns}")
            parts.append(pdf.to_csv(index=False))
        parts.append(f"Use get_table_path('{path.name}') to load this table in Python.")
        return "\n".join(parts)

    if suffix == '.parquet':
        try:
            if pl:
                df = pl.read_parquet(path, n_rows=max_rows).to_pandas()
            else:
                df = pd.read_parquet(path)
                if max_rows:
                    df = df.head(max_rows)
            columns = ', '.join(df.columns.astype(str))
            parts.append(f"Columns: {columns}")
            parts.append(df.to_csv(index=False))
            parts.append(f"Use get_table_path('{path.name}') to load this table in Python.")
            return "\n".join(parts)
        except Exception as e:
            return f"[Error reading parquet: {e}]"

    raise ValueError('Unsupported file type: %s' % path.suffix)


def answer_question_with_pandas(question: str, file_path: str | Path) -> str:
    """Return a prompt for an LLM to generate pandas code."""
    table_name = register_table(file_path)
    summary = summarize_table(file_path)
    prompt = (
        f"Table `{table_name}` preview:\n{summary}\n\n"
        f"Question: {question}\n"
        "Write pandas code to answer the question. "
        "Store the answer in the variable `result`."
    )
    return prompt


def execute_pandas_code(code: str, file_path: str | Path) -> str:
    """Execute pandas code against the provided table and return the result."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    local_vars = {}

    try:
        if suffix == '.csv':
            if pl:
                local_vars['df'] = pl.read_csv(path).to_pandas()
            else:
                local_vars['df'] = pd.read_csv(path)
        elif suffix in {'.xls', '.xlsx'}:
            xls = pd.ExcelFile(path)
            for sheet in xls.sheet_names:
                if pl:
                    local_vars[sheet] = pl.read_excel(path, sheet_id=sheet).to_pandas()
                else:
                    local_vars[sheet] = xls.parse(sheet)
        elif suffix == '.parquet':
            try:
                if pl:
                    local_vars['df'] = pl.read_parquet(path).to_pandas()
                else:
                    local_vars['df'] = pd.read_parquet(path)
            except Exception as e:
                return f'Error reading parquet: {e}'
        else:
            return f'Unsupported file type: {path.suffix}'

        exec(code, {'pd': pd}, local_vars)
        result = local_vars.get('result')
        if isinstance(result, pd.DataFrame):
            return result.head().to_csv(index=False)
        return str(result) if result is not None else 'No result'
    except Exception as e:
        return f'Error executing code: {e}'


def execute_pandas_code_by_name(code: str, table_name: str) -> str:
    """Execute code using a previously registered table name."""
    path = get_table_path(table_name)
    if not path:
        return f'Unknown table: {table_name}'
    return execute_pandas_code(code, path)
