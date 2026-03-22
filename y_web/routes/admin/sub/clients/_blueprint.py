"""Blueprint singleton and shared constants for the clients sub-package."""
from flask import Blueprint

clientsr = Blueprint("clientsr", __name__)

# Constants for opinion distribution sampling
DISTRIBUTION_SCALE_FACTOR = 10.0  # Scale factor for gamma/lognormal distributions
