"""Dataset definitions: which markets an approved dataset holds, and why.

A dataset definition lists the candidates the Owner approved from a screen
(gate 7) and one control market per candidate, drawn at random from the same
24h-volume band among markets the screen found pattern-free. Each `approve`
adds a version; markets are never removed. The definition is stored as
`dataset.json` in the dataset's directory and rendered into its card, which is
committed to the knowledge base as the provenance record backtests cite.

Control draws are reproducible: each candidate's draw is seeded from the seed
and the candidate's name, so adding candidates later leaves earlier controls
unchanged, and the same screen, candidates and seed always pick the same controls.
"""

import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from ttp.data.store import DatasetStore
from ttp.screener.wicks import MIN_EVENTS

DEFINITION_FILE = "dataset.json"
CANDIDATE, CONTROL = "candidate", "control"
BAND_WIDENINGS = 3  # how often the volume band may be widened to find a control


@dataclass(frozen=True)
class DatasetMarket:
    market: str
    role: str  # CANDIDATE or CONTROL
    paired_with: str  # a candidate's control, or a control's candidate
    version: int  # the approval that added it
    screen_id: str
    score: float
    wick_count: int
    volume_24h: float
    band: float  # volume band ratio the control was drawn from (candidates: 1)


@dataclass(frozen=True)
class Approval:
    version: int
    approved_on: str  # ISO 8601, UTC
    screen_id: str
    seed: int
    band: float
    max_control_events: int
    commit: str


@dataclass
class DatasetDefinition:
    name: str
    venue: str = "mexc"
    approvals: list[Approval] = field(default_factory=list)
    markets: list[DatasetMarket] = field(default_factory=list)

    @property
    def version(self) -> int:
        return self.approvals[-1].version if self.approvals else 0

    @property
    def candidates(self) -> list[DatasetMarket]:
        return [m for m in self.markets if m.role == CANDIDATE]

    @property
    def controls(self) -> list[DatasetMarket]:
        return [m for m in self.markets if m.role == CONTROL]

    @property
    def symbols(self) -> list[str]:
        return [m.market for m in self.markets]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "DatasetDefinition":
        raw = json.loads(text)
        return cls(
            name=raw["name"],
            venue=raw["venue"],
            approvals=[Approval(**a) for a in raw["approvals"]],
            markets=[DatasetMarket(**m) for m in raw["markets"]],
        )


def definition_path(store: DatasetStore, dataset: str) -> Path:
    return store.dataset_dir(dataset) / DEFINITION_FILE


def load_definition(store: DatasetStore, dataset: str) -> DatasetDefinition | None:
    path = definition_path(store, dataset)
    if not path.is_file():
        return None
    return DatasetDefinition.from_json(path.read_text(encoding="utf-8"))


def save_definition(store: DatasetStore, definition: DatasetDefinition) -> Path:
    path = definition_path(store, definition.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(definition.to_json(), encoding="utf-8", newline="\n")
    return path


def list_definitions(store: DatasetStore) -> list[DatasetDefinition]:
    """Every approved dataset under the store's root, by name."""
    out = []
    for path in sorted(store.root.glob(f"*/{DEFINITION_FILE}")):
        out.append(DatasetDefinition.from_json(path.read_text(encoding="utf-8")))
    return out


def load_screen_stats(reports_root: Path, screen_id: str) -> pd.DataFrame:
    """The screen's ranked table (`stats.csv`), one row per scanned market."""
    path = reports_root / screen_id / "stats.csv"
    if not path.is_file():
        raise FileNotFoundError(f"no screen {screen_id!r} at {path.as_posix()}")
    return pd.read_csv(path)


@dataclass(frozen=True)
class ControlPick:
    candidate: str
    control: str
    band: float  # ratio actually used: control volume within [v / band, v * band]


def select_controls(
    stats: pd.DataFrame,
    candidates: list[str],
    seed: int,
    band: float = 2.0,
    max_events: int = 0,
    exclude: set[str] = frozenset(),
) -> list[ControlPick]:
    """One control per candidate, drawn at random from the same volume band.

    The pool for a candidate with 24h volume v is every scanned market with at
    most `max_events` spike events, volume in [v / band, v * band], as many
    candles as the screen's fullest market (a half-listed market is trivially
    quiet), and not a candidate, an excluded market or an earlier pick. An empty
    pool widens the band (`band` squared, cubed, ...) up to `BAND_WIDENINGS`
    times; the ratio used is recorded in the pick.
    """
    if not 0 <= max_events < MIN_EVENTS:
        raise ValueError(f"max_events must be in [0, {MIN_EVENTS})")
    if band <= 1:
        raise ValueError("band must be greater than 1")
    by_market = stats.set_index("market")
    missing = [c for c in candidates if c not in by_market.index]
    if missing:
        raise ValueError(f"not in the screen: {', '.join(missing)}")
    quiet = stats[
        (stats["wick_count"] <= max_events)
        & (stats["candles"] >= stats["candles"].max())
        & ~stats["market"].isin(set(candidates) | set(exclude))
    ]
    picks: list[ControlPick] = []
    taken: set[str] = set()
    for candidate in candidates:
        v = float(by_market.loc[candidate, "volume_24h"])
        for power in range(1, BAND_WIDENINGS + 1):
            ratio = band**power
            pool = quiet[
                quiet["volume_24h"].between(v / ratio, v * ratio)
                & ~quiet["market"].isin(taken)
            ]
            if not pool.empty:
                break
        else:
            raise ValueError(
                f"no pattern-free control for {candidate} within volume band "
                f"x{band**BAND_WIDENINGS:g}"
            )
        rng = random.Random(f"{seed}/{candidate}")
        control = rng.choice(sorted(pool["market"]))
        taken.add(control)
        picks.append(ControlPick(candidate, control, ratio))
    return picks


def approve(
    definition: DatasetDefinition,
    stats: pd.DataFrame,
    screen_id: str,
    candidates: list[str],
    approved_on: datetime,
    seed: int,
    band: float,
    max_control_events: int,
    commit: str,
) -> list[DatasetMarket]:
    """Add candidates and their controls to the definition as a new version.

    Candidates already in the dataset are skipped. Returns the markets added;
    an empty list means nothing changed (and no version was added).
    """
    present = set(definition.symbols)
    new = [c for c in dict.fromkeys(candidates) if c not in present]
    if not new:
        return []
    picks = select_controls(stats, new, seed, band, max_control_events, present)
    version = definition.version + 1
    by_market = stats.set_index("market")

    def entry(market: str, role: str, paired_with: str, band_used: float):
        row = by_market.loc[market]
        return DatasetMarket(
            market=market,
            role=role,
            paired_with=paired_with,
            version=version,
            screen_id=screen_id,
            score=float(row["score"]),
            wick_count=int(row["wick_count"]),
            volume_24h=float(row["volume_24h"]),
            band=band_used,
        )

    added = []
    for p in picks:
        added.append(entry(p.candidate, CANDIDATE, p.control, 1.0))
        added.append(entry(p.control, CONTROL, p.candidate, p.band))
    definition.approvals.append(
        Approval(
            version=version,
            approved_on=approved_on.isoformat(timespec="seconds"),
            screen_id=screen_id,
            seed=seed,
            band=band,
            max_control_events=max_control_events,
            commit=commit,
        )
    )
    definition.markets.extend(added)
    return added
