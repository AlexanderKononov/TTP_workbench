"""Dataset storage: Parquet partitioned by venue / market / data type / date, read with DuckDB.

Layout under the data root (gitignored `data/datasets/` by default):

    <dataset>/venue=<venue>/market=<market>/type=<data type>/date=<YYYY-MM-DD>/*.parquet

Times are stored as naive UTC timestamps and returned tz-aware (UTC). Each data
type declares its time column, its dedup key and, if it is sampled on a fixed
grid, its interval (used to find gaps). New data types are added to
`DATA_TYPES`; the layout and reader stay the same.

Two writers share a date partition: `write` (downloads) merges into the day's
`data.parquet`, `append` (the recorder) merges into an hourly `part-HH.parquet`.
A row's file follows from its time, so a key is deduplicated within its file;
the reader simply unions every file of the partition.
"""

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

DATASET_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")


@dataclass(frozen=True)
class DataType:
    name: str
    time_column: str
    key: tuple[str, ...]
    columns: dict[str, str]  # column -> DuckDB type, in stored order
    interval: timedelta | None = None  # fixed sampling grid, if any

    @property
    def timestamp_columns(self) -> list[str]:
        """Every TIMESTAMP column: stored naive UTC, returned tz-aware."""
        return [c for c, t in self.columns.items() if t == "TIMESTAMP"]


KLINES_1M = DataType(
    name="klines_1m",
    time_column="open_time",
    key=("open_time",),
    columns={
        "open_time": "TIMESTAMP",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "DOUBLE",
        "quote_volume": "DOUBLE",
    },
    interval=timedelta(minutes=1),
)

# Public trade prints. `side` is the aggressor (taker) side, "buy" or "sell".
# MEXC gives no trade ids, so the whole row is the key: two prints identical in
# time, price, size and side collapse into one.
TRADES = DataType(
    name="trades",
    time_column="time",
    key=("time", "price", "quantity", "side"),
    columns={
        "time": "TIMESTAMP",
        "price": "DOUBLE",
        "quantity": "DOUBLE",
        "side": "VARCHAR",
    },
)

BOOK_DEPTH = 20


def _book_columns(depth: int) -> dict[str, str]:
    """Wide layout: one row per sample, `bid_price_1..depth` etc. (see `BOOK_1S`)."""
    columns = {"time": "TIMESTAMP", "version": "BIGINT"}
    for level in range(1, depth + 1):
        for column in ("bid_price", "bid_qty", "ask_price", "ask_qty"):
            columns[f"{column}_{level}"] = "DOUBLE"
    return columns


# Top of the order book once a second, sampled from the locally synced book
# (level 1 is the best price). One wide row per second rather than one row per
# level: "the best N levels at time t" is then a single-row read of 4N columns
# (DuckDB reads only the columns projected) instead of 40 rows and a pivot, and
# per-level columns barely change between seconds, so they compress to almost
# nothing. Levels a thin book lacks are NULL. `version` is the venue's book
# version the sample was taken at.
BOOK_1S = DataType(
    name="book_1s",
    time_column="time",
    key=("time",),
    columns=_book_columns(BOOK_DEPTH),
    interval=timedelta(seconds=1),
)

# The recorder's gap log: every sync state change of a market's recording
# (`kind` as in `BookEvent`, plus `start`, `stop`, `stream_error` and `missing`
# for an interval [time, until) without a synced book). Backtests read it to
# tell absent data from a quiet market.
GAPS = DataType(
    name="gaps",
    time_column="time",
    key=("time", "kind", "detail"),
    columns={
        "time": "TIMESTAMP",
        "kind": "VARCHAR",
        "until": "TIMESTAMP",
        "detail": "VARCHAR",
    },
)

DATA_TYPES = {t.name: t for t in (KLINES_1M, TRADES, BOOK_1S, GAPS)}
PART_FILE = "data.parquet"


@dataclass(frozen=True)
class Series:
    """One stored time series: a market's data of one type in a dataset."""

    venue: str
    market: str
    data_type: DataType
    first: pd.Timestamp
    last: pd.Timestamp
    rows: int


def _naive_utc(times: pd.Series) -> pd.Series:
    times = pd.to_datetime(times)
    if times.dt.tz is not None:
        times = times.dt.tz_convert("UTC").dt.tz_localize(None)
    return times.astype("datetime64[ms]")


def _bound(t: datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    if t is None:
        return None
    t = pd.Timestamp(t)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


class DatasetStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def dataset_dir(self, dataset: str) -> Path:
        if not DATASET_NAME.fullmatch(dataset):
            raise ValueError(
                f"invalid dataset name {dataset!r}: use lowercase letters, digits, '.', '_', '-'"
            )
        return self.root / dataset

    def series_dir(
        self, dataset: str, venue: str, market: str, data_type: DataType
    ) -> Path:
        return (
            self.dataset_dir(dataset)
            / f"venue={venue}"
            / f"market={market}"
            / f"type={data_type.name}"
        )

    def write(
        self,
        dataset: str,
        venue: str,
        market: str,
        data_type: DataType,
        rows: pd.DataFrame,
    ) -> int:
        """Merge rows into their date partitions; returns how many rows are new.

        Rows whose key is already stored replace the stored row, so re-running a
        download never duplicates data.
        """
        return self._merge(dataset, venue, market, data_type, rows, "%Y-%m-%d")

    def append(
        self,
        dataset: str,
        venue: str,
        market: str,
        data_type: DataType,
        rows: pd.DataFrame,
    ) -> int:
        """Merge rows into hourly part files; returns how many rows are new.

        For writers that add a little data often (the recorder): each flush
        rewrites at most the current hour's file, never the whole day.
        """
        return self._merge(dataset, venue, market, data_type, rows, "%Y-%m-%d/%H")

    def _merge(
        self,
        dataset: str,
        venue: str,
        market: str,
        data_type: DataType,
        rows: pd.DataFrame,
        bucket: str,
    ) -> int:
        if rows.empty:
            return 0
        rows = rows[list(data_type.columns)].copy()
        for column in data_type.timestamp_columns:
            rows[column] = _naive_utc(rows[column])
        base = self.series_dir(dataset, venue, market, data_type)
        added = 0
        buckets = rows[data_type.time_column].dt.strftime(bucket)
        for key, part in rows.groupby(buckets, sort=True):
            day, _, hour = key.partition("/")
            name = f"part-{hour}.parquet" if hour else PART_FILE
            path = base / f"date={day}" / name
            stored = self._read_files([path], data_type) if path.exists() else None
            merged = pd.concat([d for d in (stored, part) if d is not None])
            merged = merged.drop_duplicates(list(data_type.key), keep="last")
            merged = merged.sort_values(data_type.time_column)
            added += len(merged) - (0 if stored is None else len(stored))
            self._write_file(path, merged, data_type)
        return added

    def read(
        self,
        dataset: str,
        venue: str,
        market: str,
        data_type: DataType,
        start: datetime | pd.Timestamp | None = None,
        end: datetime | pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Rows with start <= time < end, ordered by time; times tz-aware UTC."""
        start, end = _bound(start), _bound(end)
        files = self._files(dataset, venue, market, data_type, start, end)
        df = self._read_files(files, data_type, start, end)
        for column in data_type.timestamp_columns:
            df[column] = df[column].dt.tz_localize("UTC")
        return df.reset_index(drop=True)

    def series(self, dataset: str) -> list[Series]:
        """Every stored series in a dataset, with its time range and row count."""
        out = []
        for type_dir in sorted(
            self.dataset_dir(dataset).glob("venue=*/market=*/type=*")
        ):
            data_type = DATA_TYPES.get(type_dir.name.removeprefix("type="))
            if data_type is None:
                continue
            venue = type_dir.parent.parent.name.removeprefix("venue=")
            market = type_dir.parent.name.removeprefix("market=")
            df = self.read(dataset, venue, market, data_type)
            if df.empty:
                continue
            times = df[data_type.time_column]
            out.append(
                Series(venue, market, data_type, times.iloc[0], times.iloc[-1], len(df))
            )
        return out

    def gaps(
        self, dataset: str, venue: str, market: str, data_type: DataType
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """Missing intervals [start, end) between the first and last stored row.

        Only for data types on a fixed grid; others return no gaps.
        """
        if data_type.interval is None:
            return []
        times = self.read(dataset, venue, market, data_type)[data_type.time_column]
        step = pd.Timedelta(data_type.interval)
        nxt = times.shift(-1)
        holes = (nxt - times) > step
        return [(t + step, n) for t, n in zip(times[holes], nxt[holes], strict=True)]

    def _files(
        self,
        dataset: str,
        venue: str,
        market: str,
        data_type: DataType,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> list[Path]:
        first_day = start.date() if start is not None else date.min
        last_day = end.date() if end is not None else date.max
        files = []
        base = self.series_dir(dataset, venue, market, data_type)
        for day_dir in sorted(base.glob("date=*")):
            day = date.fromisoformat(day_dir.name.removeprefix("date="))
            if first_day <= day <= last_day:
                files.extend(sorted(day_dir.glob("*.parquet")))
        return files

    @staticmethod
    def _read_files(
        files: list[Path],
        data_type: DataType,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        cols = ", ".join(f'"{c}"' for c in data_type.columns)
        if not files:
            # Own connection: the module-level default one is not thread-safe.
            with duckdb.connect() as con:
                return con.sql(
                    "SELECT "
                    + ", ".join(
                        f'NULL::{t} AS "{c}"' for c, t in data_type.columns.items()
                    )
                    + " LIMIT 0"
                ).df()
        t = f'"{data_type.time_column}"'
        where, params = [], {"files": [f.as_posix() for f in files]}
        if start is not None:
            where.append(f"{t} >= $start")
            params["start"] = start.to_pydatetime()
        if end is not None:
            where.append(f"{t} < $end")
            params["end"] = end.to_pydatetime()
        sql = f"SELECT {cols} FROM read_parquet($files)"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {t}"
        with duckdb.connect() as con:
            return con.execute(sql, params).df()

    @staticmethod
    def _write_file(path: Path, rows: pd.DataFrame, data_type: DataType) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        target = tmp.as_posix().replace("'", "''")
        casts = ", ".join(
            f'CAST("{c}" AS {t}) AS "{c}"' for c, t in data_type.columns.items()
        )
        with duckdb.connect() as con:
            con.register("rows_in", rows)
            con.execute(
                f"COPY (SELECT {casts} FROM rows_in) TO '{target}' (FORMAT parquet)"
            )
        os.replace(tmp, path)
