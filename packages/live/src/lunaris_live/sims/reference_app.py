from ..session.schema.sim_app import SimApp
from .schema.contract import SimContract
from .schema.parameter import SimParameter


def reference_app() -> SimApp:
    """Known linear instrument for contract tests; never selected by topic guessing."""
    return SimApp(
        app_id="linear-reference",
        url="/api/live/sims/linear-reference",
        title="A linear relationship",
        contract=SimContract(
            objective="Compare how y changes when x changes in y = 2x.",
            parameters={"x": SimParameter(label="x", minimum=0, maximum=10, step=1, default=2)},
        ),
    )
