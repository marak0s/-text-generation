from pathlib import Path
import re

try:  # pragma: no cover - pandas is an optional dependency at runtime
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    import polars as pl
except Exception:  # pragma: no cover - optional dependency
    pl = None

_loaded_tables: dict[str, str] = {}
# Cache loaded DataFrames so subsequent queries do not reread large
# datasets from disk. Keys are the registered table names.
_table_cache: dict[str, "pd.DataFrame"] = {}


def _preload_table(path: Path) -> None:
    """Load the entire table into cache so pandas queries use full data."""
    name = path.name
    if name in _table_cache:
        return
    try:
        suffix = path.suffix.lower()
        if suffix == '.csv':
            if pl:
                _table_cache[name] = pl.read_csv(path).to_pandas()
            else:
                _table_cache[name] = pd.read_csv(path, low_memory=False)
        elif suffix in {'.xls', '.xlsx'}:
            xls = pd.ExcelFile(path)
            sheets = {}
            for sheet in xls.sheet_names:
                if pl:
                    try:
                        sheets[sheet] = pl.read_excel(path, sheet_name=sheet).to_pandas()
                    except Exception:
                        sheets[sheet] = xls.parse(sheet)
                else:
                    sheets[sheet] = xls.parse(sheet)
            _table_cache[name] = sheets
        elif suffix == '.parquet':
            if pl:
                _table_cache[name] = pl.read_parquet(path).to_pandas()
            else:
                _table_cache[name] = pd.read_parquet(path)
    except Exception:
        pass


def register_table(file_path: str | Path) -> str:
    """Register a table path and return its name identifier.

    Besides the exact file name, a secondary alias without leading digits
    and separators is registered. This allows referencing files like
    ``"1_2 - LeadTime.parquet"`` simply as ``"LeadTime.parquet"``.
    """
    path = Path(file_path).resolve()
    name = path.name
    _loaded_tables[name] = str(path)
    alias = re.sub(r'^[\s\-_\d]+', '', name)
    if alias != name and alias not in _loaded_tables:
        _loaded_tables[alias] = str(path)
    return name


def get_table_path(name: str) -> str | None:
    """Return the registered path for a table name if available."""
    return _loaded_tables.get(name)


def load_table(name: str):
    """Return a cached table by name, loading it from disk if necessary.

    For Excel files, returns a dict mapping sheet names to DataFrames.
    Raises FileNotFoundError if the table name is unknown or cannot be
    loaded.
    """
    path_str = get_table_path(name)
    if not path_str:
        raise FileNotFoundError(f"Неизвестная таблица: {name}")
    path = Path(path_str)
    if name not in _table_cache:
        _preload_table(path)
    if name in _table_cache:
        return _table_cache[name]
    raise FileNotFoundError(f"Не удалось загрузить таблицу: {name}")


def _truncate_frame(df: "pd.DataFrame", limit: int) -> "pd.DataFrame":
    """Return a copy of ``df`` with each cell truncated to ``limit`` characters."""
    if limit:
        df_str = df.astype(str)
        truncate = lambda x: x[:limit] + ("..." if len(x) > limit else "")
        # pandas <2.1 does not expose DataFrame.map and using applymap
        # raises a FutureWarning in newer versions. Use column-wise map to
        # remain compatible across pandas releases without emitting warnings.
        if hasattr(df_str, "map"):
            return df_str.map(truncate)
        return df_str.apply(lambda col: col.map(truncate))
    return df


def _count_uniques_csv(path: Path, columns) -> dict[str, int]:
    """Return the number of unique values for each column in a CSV file.

    The CSV is processed in chunks to avoid loading the entire file into
    memory at once, enabling handling of very large files.
    """
    uniques_sets: dict[str, set] = {c: set() for c in columns}
    for chunk in pd.read_csv(path, dtype=str, usecols=columns, chunksize=10000):
        for col in columns:
            uniques_sets[col].update(chunk[col].dropna().astype(str).unique())
    return {col: len(vals) for col, vals in uniques_sets.items()}


def summarize_table(file_path: str, max_rows: int = 5, cell_limit: int = 80) -> str:
    """Return a lightweight textual preview of an Excel, CSV or Parquet table."""
    if pd is None:
        return '[pandas не установлен]'
    path = Path(file_path)
    # Register the table so ``get_table_path`` can resolve it later
    register_table(path)
    parts = [f"Таблица: {path.name}"]
    suffix = path.suffix.lower()

    if suffix == '.csv':
        row_count = None
        df = None
        if pl:
            try:
                scan = pl.scan_csv(path)
                df = scan.head(max_rows).collect().to_pandas()
                uniq_df = (
                    scan.select([pl.col(c).n_unique().alias(str(c)) for c in df.columns])
                    .collect()
                    .to_pandas()
                )
                uniques = {col: int(uniq_df.iloc[0][col]) for col in uniq_df.columns}
            except Exception:  # pragma: no cover - fallback to pandas
                df = None
                uniques = {}
        else:
            uniques = {}
        if df is None:
            df = pd.read_csv(path, nrows=max_rows, low_memory=False)
            types = df.dtypes.astype(str).to_dict()
            df = df.astype(str)
            try:
                uniques = _count_uniques_csv(path, df.columns)
            except Exception:
                uniques = {}
        else:
            types = df.dtypes.astype(str).to_dict()
            df = df.astype(str)
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                row_count = sum(1 for _ in fh) - 1
        except Exception:
            row_count = None
        df = _truncate_frame(df, cell_limit)
        columns = ', '.join(str(c) for c in df.columns)
        parts.append(f"Столбцы: {columns}")
        parts.append("Типы: " + ", ".join(f"{k}={v}" for k, v in types.items()))
        parts.append(df.to_csv(index=False))
        if row_count is not None:
            parts.append(f"Строки: {row_count}")
        if uniques:
            parts.append(
                "Уникальные значения: " + ", ".join(f"{k}={v}" for k, v in uniques.items())
            )
        parts.append(
            f"Используйте load_table('{path.name}') для загрузки полной таблицы (или get_table_path('{path.name}') для пути). "
            f"Предпросмотр ограничен {max_rows} строками и {cell_limit} символами в ячейке, поэтому не делайте по нему выводов. "
            "Всегда проверяйте df.dtypes и при необходимости преобразуйте столбцы (например, pd.to_datetime) перед фильтрацией. "
            "Заключайте анализ в блоки ```python```."
        )
        _preload_table(path)
        return "\n".join(parts)

    if suffix in {'.xls', '.xlsx'}:
        xls = pd.ExcelFile(path)
        try:
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception:  # pragma: no cover - optional dependency
            wb = None
        for sheet in xls.sheet_names:
            row_count = None
            uniques = {}
            if pl:
                try:
                    full = pl.read_excel(path, sheet_name=sheet)
                    row_count = full.height
                    pdf = full.head(max_rows).to_pandas()
                    uniq_df = full.select(pl.all().n_unique()).to_pandas()
                    uniques = {col: int(uniq_df.iloc[0][col]) for col in uniq_df.columns}
                except Exception:  # pragma: no cover - fallback to pandas
                    pdf = None
            else:
                pdf = None
            if pdf is None:
                full_pd = xls.parse(sheet)
                row_count = len(full_pd)
                pdf = full_pd.head(max_rows)
                try:
                    uniques = full_pd.nunique(dropna=False).to_dict()
                except Exception:
                    uniques = {}
            types = pdf.dtypes.astype(str).to_dict()
            pdf = _truncate_frame(pdf, cell_limit)
            columns = ', '.join(str(c) for c in pdf.columns)
            if row_count is not None:
                parts.append(f"Лист: {sheet} ({row_count} строк)")
            else:
                parts.append(f"Лист: {sheet}")
            parts.append(f"Столбцы: {columns}")
            parts.append("Типы: " + ", ".join(f"{k}={v}" for k, v in types.items()))
            parts.append(pdf.to_csv(index=False))
            if uniques:
                parts.append(
                    "Уникальные значения: " + ", ".join(f"{k}={v}" for k, v in uniques.items())
                )
        parts.append(
            f"Используйте load_table('{path.name}') для загрузки полной таблицы (или get_table_path('{path.name}') для пути). "
            f"Предпросмотр ограничен {max_rows} строками и {cell_limit} символами в ячейке, поэтому не делайте по нему выводов. "
            "Всегда проверяйте df.dtypes и при необходимости преобразуйте столбцы (например, pd.to_datetime) перед фильтрацией. "
            "Заключайте анализ в блоки ```python```."
        )
        _preload_table(path)
        return "\n".join(parts)

    if suffix == '.parquet':
        try:
            import pyarrow.parquet as pq  # type: ignore
        except Exception:  # pragma: no cover
            pq = None
        try:
            row_count = None
            df = None
            if pq is not None:
                try:
                    row_count = pq.ParquetFile(path).metadata.num_rows
                except Exception:
                    row_count = None
            uniques = {}
            if pl:
                try:
                    scan = pl.scan_parquet(path)
                    df = scan.head(max_rows).collect().to_pandas()
                    uniq_df = scan.select(
                        [pl.col(c).n_unique().alias(str(c)) for c in df.columns]
                    ).collect().to_pandas()
                    uniques = {col: int(uniq_df.iloc[0][col]) for col in uniq_df.columns}
                except Exception:
                    df = None
            else:
                df = None
            if df is None:
                df = pd.read_parquet(path)
                if row_count is None:
                    row_count = len(df)
                if max_rows:
                    df = df.head(max_rows)
                try:
                    uniques = pd.read_parquet(path).nunique(dropna=False).to_dict()
                except Exception:
                    uniques = {}
            types = df.dtypes.astype(str).to_dict()
            df = _truncate_frame(df, cell_limit)
            columns = ', '.join(str(c) for c in df.columns)
            parts.append(f"Столбцы: {columns}")
            parts.append("Типы: " + ", ".join(f"{k}={v}" for k, v in types.items()))
            parts.append(df.to_csv(index=False))
            if row_count is not None:
                parts.append(f"Строки: {row_count}")
            if uniques:
                parts.append(
                    "Уникальные значения: " + ", ".join(f"{k}={v}" for k, v in uniques.items())
                )
            parts.append(
                f"Используйте load_table('{path.name}') для загрузки полной таблицы (или get_table_path('{path.name}') для пути). "
                f"Предпросмотр ограничен {max_rows} строками и {cell_limit} символами в ячейке, поэтому не делайте по нему выводов. "
                "Всегда проверяйте df.dtypes и при необходимости преобразуйте столбцы (например, pd.to_datetime) перед фильтрацией. "
                "Заключайте анализ в блоки ```python```."
            )
            _preload_table(path)
            return "\n".join(parts)
        except Exception as e:
            return f"[Ошибка чтения parquet: {e}]"

    raise ValueError('Неподдерживаемый тип файла: %s' % path.suffix)


def answer_question_with_pandas(question: str, file_path: str | Path) -> str:
    """Return a prompt for an LLM to generate pandas code."""
    if pd is None:
        raise RuntimeError('Для работы с таблицами требуется pandas')
    table_name = register_table(file_path)
    summary = summarize_table(file_path)
    prompt = (
        f"Предпросмотр таблицы `{table_name}`:\n{summary}\n\n"
        f"Вопрос: {question}\n"
        "Ответ должен опираться на полный набор данных, а не на предпросмотр. "
        f"Получите DataFrame через load_table('{table_name}') (не используйте pd.read_* по пути файла). "
        "Перед фильтрацией проверьте df.dtypes и при необходимости преобразуйте столбцы, например pd.to_datetime. "
        "Сохраните ответ в переменную `result` и отвечайте на том же языке, что и вопрос."
    )
    return prompt


def execute_pandas_code(
    code: str,
    file_path: str | Path | None,
    max_output_rows: int | None = 100,
    cell_limit: int = 80,
) -> str:
    """Execute pandas code against the provided table and return the result."""
    if pd is None:
        return 'требуется pandas'
    if not file_path:
        return 'Не указан путь к файлу'
    path = Path(file_path)
    if not path.exists():
        alt = get_table_path(path.name)
        if alt:
            path = Path(alt)
        else:
            return f'Файл не найден: {path}'
    suffix = path.suffix.lower()
    local_vars = {}
    name = path.name

    try:
        if suffix == '.csv':
            if name in _table_cache:
                local_vars['df'] = _table_cache[name]
            else:
                if pl:
                    try:
                        df = pl.scan_csv(path).collect().to_pandas()
                    except Exception:
                        df = pd.read_csv(path, low_memory=False)
                else:
                    df = pd.read_csv(path, low_memory=False)
                _table_cache[name] = df
                local_vars['df'] = df
        elif suffix in {'.xls', '.xlsx'}:
            if name in _table_cache:
                sheets = _table_cache[name]
            else:
                xls = pd.ExcelFile(path)
                sheets = {}
                for sheet in xls.sheet_names:
                    if pl:
                        try:
                            sheets[sheet] = pl.read_excel(path, sheet_name=sheet).to_pandas()
                        except Exception:
                            sheets[sheet] = xls.parse(sheet)
                    else:
                        sheets[sheet] = xls.parse(sheet)
                _table_cache[name] = sheets
            local_vars.update(sheets)
        elif suffix == '.parquet':
            if name in _table_cache:
                local_vars['df'] = _table_cache[name]
            else:
                try:
                    if pl:
                        try:
                            df = pl.scan_parquet(path).collect().to_pandas()
                        except Exception:
                            df = pd.read_parquet(path)
                    else:
                        df = pd.read_parquet(path)
                except Exception as e:
                    return f'Ошибка чтения parquet: {e}'
                _table_cache[name] = df
                local_vars['df'] = df
        else:
            return f'Неподдерживаемый тип файла: {path.suffix}'

        exec(code, {'pd': pd}, local_vars)
        result = local_vars.get('result')
        if isinstance(result, pd.DataFrame):
            if max_output_rows is not None and len(result) > max_output_rows:
                head = _truncate_frame(result.head(max_output_rows), cell_limit).to_csv(
                    index=False
                )
                return f"{head}\n... ({len(result) - max_output_rows} more rows)"
            return _truncate_frame(result, cell_limit).to_csv(index=False)
        return str(result) if result is not None else 'Нет результата'
    except Exception as e:
        return f'Ошибка выполнения кода: {e}'


def execute_pandas_code_by_name(code: str, table_name: str) -> str:
    """Execute code using a previously registered table name."""
    path = get_table_path(table_name)
    if not path:
        return f'Неизвестная таблица: {table_name}'
    return execute_pandas_code(code, path)
