"""Pydantic data models used in API responses.

These models define the structure of room status information returned
from the API. They are separate from the Google API data structures
to decouple our internal representation from external dependencies.
"""

from pydantic import BaseModel
from typing import Optional, List


class BusyBlock(BaseModel):
    """Represents a busy time block for a room calendar."""

    start: str
    end: str


class RoomStatus(BaseModel):
    """Represents the computed status of a room at a point in time."""

    roomId: str
    roomName: str
    buildingId: Optional[str] = None
    floorName: Optional[str] = None
    capacity: Optional[int] = None

    isBusyNow: bool
    isSoon: bool
    nextChangeIso: Optional[str] = None
    busyBlocks: List[BusyBlock] = []