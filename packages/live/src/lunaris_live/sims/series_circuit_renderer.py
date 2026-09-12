import math
from importlib.resources import files

from .schema.teaching_spec import TeachingSpec


class SeriesCircuitRenderer:
    """A supported physical recipe; the generator cannot author its circuit connections."""

    version = "series-resistor-v1"
    marker = '<div data-lunaris-renderer="series-resistor-v1"></div>'

    def validate(self, spec: TeachingSpec) -> None:
        parameters = spec.contract.parameters
        if set(parameters) != {"voltage", "resistance"}:
            raise ValueError("The series recipe needs voltage and resistance controls")
        if parameters["voltage"].minimum < 0 or parameters["resistance"].minimum <= 0:
            raise ValueError(
                "The series recipe requires nonnegative voltage and positive resistance"
            )
        for case in spec.cases:
            actual = float(case.outputs.get("current", "nan"))
            expected = case.state["voltage"] / case.state["resistance"]
            if not math.isclose(actual, expected, abs_tol=0.005):
                raise ValueError("The recipe is only for the ideal I=V/R relationship")

    def assemble(self, html: str, spec: TeachingSpec) -> str:
        self.validate(spec)
        if html.count(self.marker) != 1 or "data-lunaris-renderer-code" in html:
            raise ValueError("Use exactly the empty series circuit mount; do not copy its code")
        script = self._script()
        index = html.lower().rfind("</body>")
        return html[:index] + script + html[index:] if index >= 0 else html + script

    def detect(self, html: str) -> bool:
        if "data-lunaris-renderer" not in html:
            return False
        if html.count(self._script()) != 1 or html.count(self.marker) != 1:
            raise ValueError("The assembled circuit renderer is missing or has been modified")
        return True

    def template(self) -> str:
        source = files("lunaris_live.sims").joinpath("series_circuit.js").read_text()
        return source.split("root.innerHTML = `", 1)[1].split("`;", 1)[0]

    def _script(self) -> str:
        source = files("lunaris_live.sims").joinpath("series_circuit.js").read_text()
        return f'<script data-lunaris-renderer-code="{self.version}">{source}</script>'
