"""Sign-up targets (who is sent to which module when registering)."""

from ._forward import forward

TRAINING = "training"  # checked against y_web.src.signup.TRAINING by the contract test

is_target = forward(
    "y_web.src.signup",
    "is_target",
    name="is_target",
    doc="Whether a user is a sign-up target of a module.",
)
is_anonymous = forward(
    "y_web.src.signup",
    "is_anonymous",
    name="is_anonymous",
    doc="Whether the sign-up of a user is anonymous.",
)
is_enabled = forward(
    "y_web.src.signup",
    "is_enabled",
    name="is_enabled",
    doc="Whether sign-up is switched on for the site.",
)
set_target = forward(
    "y_web.src.signup",
    "set_target",
    name="set_target",
    doc="Make a user a sign-up target of a module (or not).",
)
set_anonymous = forward(
    "y_web.src.signup",
    "set_anonymous",
    name="set_anonymous",
    doc="Make the sign-up of a user anonymous (or not).",
)

__all__ = [
    "TRAINING",
    "is_anonymous",
    "is_enabled",
    "is_target",
    "set_anonymous",
    "set_target",
]
