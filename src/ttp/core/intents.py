"""Order intents: a strategy's requests to the broker.

An intent becomes an order only if the broker accepts it. The strategy names each
order with a `client_id` of its own (see `Strategy.next_client_id`), so it can
cancel without waiting for a venue id. MEXC has no amend: a requote is a `Cancel`
followed by a `PlaceLimit`.
"""

from dataclasses import dataclass

from ttp.core.events import Market, Side


@dataclass(frozen=True, slots=True)
class PlaceLimit:
    market: Market
    client_id: str
    side: Side
    price: float
    quantity: float


@dataclass(frozen=True, slots=True)
class Cancel:
    market: Market
    client_id: str


OrderIntent = PlaceLimit | Cancel
