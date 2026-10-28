"""Decoding of MEXC's protobuf push frames without a protobuf toolchain. Pure.

MEXC's spot WebSocket pushes binary proto3 messages wrapped in
`PushDataV3ApiWrapper` (github.com/mexcdevelop/websocket-proto, read
2026-10-28). The streams we use have only strings, varints and nested messages,
so a schema-driven reader of the proto3 wire format covers them in a few lines
and nothing has to be generated. Field numbers below are transcribed from the
`.proto` files; `tests/fixtures/mexc/ws_frames_*.json` holds frames captured
from the live stream to prove the transcription.
"""

from dataclasses import dataclass
from typing import Any

from ttp.venues.mexc.book import DepthDiff, Level, Trade

# Wire types of the proto3 encoding.
_VARINT, _FIXED64, _LEN, _FIXED32 = 0, 1, 2, 5


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # "string" | "int" | "message"
    schema: dict[int, "Field"] | None = None
    repeated: bool = False


class ProtoError(ValueError):
    """A frame is not a well-formed message of the expected schema."""


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value, shift = 0, 0
    while True:
        if pos >= len(data):
            raise ProtoError("truncated varint")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def decode_message(data: bytes, schema: dict[int, Field]) -> dict[str, Any]:
    """Decode `data` by `schema`; unknown fields are skipped, repeated ones listed."""
    out: dict[str, Any] = {f.name: [] for f in schema.values() if f.repeated}
    pos = 0
    while pos < len(data):
        tag, pos = _varint(data, pos)
        number, wire = tag >> 3, tag & 0x7
        value: Any
        if wire == _VARINT:
            value, pos = _varint(data, pos)
        elif wire == _LEN:
            length, pos = _varint(data, pos)
            value, pos = data[pos : pos + length], pos + length
            if len(value) != length:
                raise ProtoError("truncated length-delimited field")
        elif wire == _FIXED64:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == _FIXED32:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ProtoError(f"unsupported wire type {wire}")
        field = schema.get(number)
        if field is None:
            continue
        if field.kind == "string":
            value = value.decode("utf-8")
        elif field.kind == "message":
            value = decode_message(value, field.schema or {})
        elif field.kind != "int":
            raise ProtoError(f"unknown field kind {field.kind}")
        if field.repeated:
            out[field.name].append(value)
        else:
            out[field.name] = value
    return out


LEVEL = {1: Field("price", "string"), 2: Field("quantity", "string")}
AGGRE_DEPTHS = {
    1: Field("asks", "message", LEVEL, repeated=True),
    2: Field("bids", "message", LEVEL, repeated=True),
    3: Field("eventType", "string"),
    4: Field("fromVersion", "string"),
    5: Field("toVersion", "string"),
    6: Field("lastOrderCreateTime", "int"),
}
DEAL = {
    1: Field("price", "string"),
    2: Field("quantity", "string"),
    3: Field("tradeType", "int"),  # 1 buy, 2 sell
    4: Field("time", "int"),
    5: Field("tradeId", "string"),
}
AGGRE_DEALS = {
    1: Field("deals", "message", DEAL, repeated=True),
    2: Field("eventType", "string"),
}
WRAPPER = {
    1: Field("channel", "string"),
    3: Field("symbol", "string"),
    4: Field("symbolId", "string"),
    5: Field("createTime", "int"),
    6: Field("sendTime", "int"),
    313: Field("publicAggreDepths", "message", AGGRE_DEPTHS),
    314: Field("publicAggreDeals", "message", AGGRE_DEALS),
}


def _levels(items: list[dict[str, str]]) -> tuple[Level, ...]:
    return tuple(Level(float(i["price"]), float(i["quantity"])) for i in items)


def decode_push(frame: bytes) -> DepthDiff | list[Trade] | None:
    """Decode one binary frame into a depth diff or trades; None for other bodies."""
    try:
        msg = decode_message(frame, WRAPPER)
        if "publicAggreDepths" in msg:
            body = msg["publicAggreDepths"]
            return DepthDiff(
                market=msg["symbol"],
                from_version=int(body["fromVersion"]),
                to_version=int(body["toVersion"]),
                bids=_levels(body["bids"]),
                asks=_levels(body["asks"]),
                time_ms=int(msg.get("sendTime", 0)),
            )
        if "publicAggreDeals" in msg:
            return [
                Trade(
                    market=msg["symbol"],
                    price=float(d["price"]),
                    quantity=float(d["quantity"]),
                    side="buy" if d["tradeType"] == 1 else "sell",
                    time_ms=int(d["time"]),
                    trade_id=d.get("tradeId", ""),
                )
                for d in msg["publicAggreDeals"]["deals"]
            ]
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise ProtoError(f"malformed MEXC push frame: {exc}") from exc
    return None
