from Options import Range, StartInventoryPool, PerGameCommonOptions
from dataclasses import dataclass


class ChapterClears(Range):
    """
    This determines how many chapter clears are required to enter the Palace of Shadow.
    """
    display_name = "Required Chapter Clears"
    range_start = 0
    range_end = 7
    default = 7


@dataclass
class TTYDOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    chapter_clears: ChapterClears
