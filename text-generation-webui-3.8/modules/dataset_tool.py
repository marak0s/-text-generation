from pathlib import Path

try:  # pragma: no cover - pandas is an optional dependency at runtime
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

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


def _truncate_frame(df: "pd.DataFrame", limit: int) -> "pd.DataFrame":
    """Return a copy of ``df`` with each cell truncated to ``limit`` characters."""
    if limit:
        return df.astype(str).applymap(
            lambda x: x[:limit] + ("..." if len(x) > limit else "")
        )
    return df


def summarize_table(file_path: str, max_rows: int = 5, cell_limit: int = 80) -> str:
    """Return a lightweight textual preview of an Excel, CSV or Parquet table."""
    if pd is None:
        return '[pandas not installed]'
    path = Path(file_path)
    parts = [f"Table: {path.name}"]
    suffix = path.suffix.lower()

    if suffix == '.csv':
        df = None
        if pl:
            try:
                df = (
                    pl.scan_csv(path, ignore_errors=True)
                    .head(max_rows)
                    .collect()
                    .to_pandas()
                )
            except Exception:  # pragma: no cover - fallback to pandas
                df = None
        if df is None:
            df = pd.read_csv(path, nrows=max_rows, dtype=str)
        df = _truncate_frame(df, cell_limit)
        columns = ', '.join(str(c) for c in df.columns)
        parts.append(f"Columns: {columns}")
        parts.append(df.to_csv(index=False))
        parts.append(
            f"Use get_table_path('{path.name}') to load this table in Python. "
            f"Preview limited to {max_rows} rows and {cell_limit} chars per cell."
        )
        return "\n".join(parts)

    if suffix in {'.xls', '.xlsx'}:
        xls = pd.ExcelFile(path)
        for sheet in xls.sheet_names:
            pdf = None
            if pl:
                try:
                    pdf = pl.read_excel(path, sheet_name=sheet, n_rows=max_rows).to_pandas()
                except Exception:  # pragma: no cover - fallback to pandas
                    pdf = None
            if pdf is None:
                pdf = xls.parse(sheet, nrows=max_rows)
            pdf = _truncate_frame(pdf, cell_limit)
            columns = ', '.join(str(c) for c in pdf.columns)
            parts.append(f"Sheet: {sheet}")
            parts.append(f"Columns: {columns}")
            parts.append(pdf.to_csv(index=False))
        parts.append(
            f"Use get_table_path('{path.name}') to load this table in Python. "
            f"Preview limited to {max_rows} rows and {cell_limit} chars per cell."
        )
        return "\n".join(parts)

    if suffix == '.parquet':
        try:
            df = None
            if pl:
                try:
                    df = (
                        pl.scan_parquet(path)
                        .head(max_rows)
                        .collect()
                        .to_pandas()
                    )
                except Exception:
                    df = None
            if df is None:
                df = pd.read_parquet(path)
                if max_rows:
                    df = df.head(max_rows)
            df = _truncate_frame(df, cell_limit)
            columns = ', '.join(str(c) for c in df.columns)
            parts.append(f"Columns: {columns}")
            parts.append(df.to_csv(index=False))
            parts.append(
                f"Use get_table_path('{path.name}') to load this table in Python. "
                f"Preview limited to {max_rows} rows and {cell_limit} chars per cell."
            )
            return "\n".join(parts)
        except Exception as e:
            return f"[Error reading parquet: {e}]"

    raise ValueError('Unsupported file type: %s' % path.suffix)


def answer_question_with_pandas(question: str, file_path: str | Path) -> str:
    """Return a prompt for an LLM to generate pandas code."""
    if pd is None:
        raise RuntimeError('pandas is required for table questions')
    table_name = register_table(file_path)
    summary = summarize_table(file_path)
    prompt = (
        f"Table `{table_name}` preview:\n{summary}\n\n"
        f"Question: {question}\n"
        "Write pandas code to answer the question. "
        "Store the answer in the variable `result`."
    )
    return prompt


def execute_pandas_code(
    code: str,
    file_path: str | Path,
    max_output_rows: int | None = 20,
    cell_limit: int = 80,
) -> str:
    """Execute pandas code against the provided table and return the result."""
    if pd is None:
        return 'pandas is required'
    path = Path(file_path)
    suffix = path.suffix.lower()
    local_vars = {}

    try:
        if suffix == '.csv':
            if pl:
                try:
                    local_vars['df'] = pl.scan_csv(path, ignore_errors=True).collect().to_pandas()
                except Exception:
                    local_vars['df'] = pd.read_csv(path)
            else:
                local_vars['df'] = pd.read_csv(path)
        elif suffix in {'.xls', '.xlsx'}:
            xls = pd.ExcelFile(path)
            for sheet in xls.sheet_names:
                if pl:
                    try:
                        local_vars[sheet] = pl.read_excel(path, sheet_name=sheet).to_pandas()
                    except Exception:
                        local_vars[sheet] = xls.parse(sheet)
                else:
                    local_vars[sheet] = xls.parse(sheet)
        elif suffix == '.parquet':
            try:
                if pl:
                    try:
                        local_vars['df'] = pl.scan_parquet(path).collect().to_pandas()
                    except Exception:
                        local_vars['df'] = pd.read_parquet(path)
                else:
                    local_vars['df'] = pd.read_parquet(path)
            except Exception as e:
                return f'Error reading parquet: {e}'
        else:
            return f'Unsupported file type: {path.suffix}'

        exec(code, {'pd': pd}, local_vars)
        result = local_vars.get('result')
        if isinstance(result, pd.DataFrame):
            if max_output_rows is not None and len(result) > max_output_rows:
                head = _truncate_frame(result.head(max_output_rows), cell_limit).to_csv(
                    index=False
                )
                return f"{head}\n... ({len(result) - max_output_rows} more rows)"
            return _truncate_frame(result, cell_limit).to_csv(index=False)
        return str(result) if result is not None else 'No result'
    except Exception as e:
        return f'Error executing code: {e}'


def execute_pandas_code_by_name(code: str, table_name: str) -> str:
    """Execute code using a previously registered table name."""
    path = get_table_path(table_name)
    if not path:
        return f'Unknown table: {table_name}'
    return execute_pandas_code(code, path)
