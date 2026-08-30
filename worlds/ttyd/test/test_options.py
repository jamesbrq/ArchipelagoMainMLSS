"""Option-matrix generation tests for the fine-grained region graph."""
from . import TTYDTestBase


class TestDefault(TTYDTestBase):
    options = {}


class TestPalaceSkip(TTYDTestBase):
    options = {"palace_skip": True}


class TestLimitChapterLogic(TTYDTestBase):
    options = {"limit_chapter_logic": True}


class TestLimitChapterEight(TTYDTestBase):
    options = {"limit_chapter_eight": True}


class TestNoBluePipes(TTYDTestBase):
    options = {"blue_pipe_toggle": False}


class TestOpenWestside(TTYDTestBase):
    options = {"open_westside": True}


class TestTattlesanity(TTYDTestBase):
    options = {"tattlesanity": True}


class TestGoalStars(TTYDTestBase):
    options = {"goal": "crystal_stars"}


class TestGoalBonetail(TTYDTestBase):
    options = {"goal": "bonetail", "pit_items": "all"}


class TestKitchenSink(TTYDTestBase):
    options = {
        "limit_chapter_logic": True,
        "limit_chapter_eight": True,
        "tattlesanity": True,
        "troublesanity": True,
        "cooksanity": True,
        "piecesanity": "all",
        "keysanity": True,
        "shopsanity": True,
        "open_westside": True,
        "blue_pipe_toggle": False,
    }
