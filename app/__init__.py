"""Sports betting model — NBA / MLB / NHL prop EV engine.

Runs as a series of scheduled GitHub Actions jobs that pull free public data,
train per-(sport, market) models, compute EV vs sportsbook lines, and write
JSON artifacts that the static dashboard in docs/ reads from.

Nothing in this package needs a paid API key or hosted server.
"""

__version__ = "0.1.0"
