from .mlb import MLBProvider
from .nba import NBAProvider
from .nhl import NHLProvider
from .odds import OddsAPIClient
from .free_odds import FreeOddsAggregator

PROVIDERS = {
    "MLB": MLBProvider,
    "NBA": NBAProvider,
    "NHL": NHLProvider,
}
