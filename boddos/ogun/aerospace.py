"""Rocket flight simulation for Ogun 3D's aerospace stack, via RocketPy —
a real 6-DOF flight simulator (used by university rocketry teams), not a
back-of-envelope estimate.

Scoped to a constant-thrust motor approximation (`RocketPy.GenericMotor`
with a flat thrust curve derived from total impulse ÷ burn time) rather
than full grain-geometry motor design — that keeps the input a handful
of numbers an LLM can reliably fill in from "small model rocket, medium
motor" style descriptions, while still running RocketPy's real
aerodynamics, mass properties, and atmosphere model underneath.

Airfoil analysis (XFOIL) and full aircraft geometry (OpenVSP) are
deliberately not wired up yet — the Ubuntu-packaged `xfoil` binary
crashes with SIGFPE mid-solve in this environment (a real bug in that
build, reproduced while evaluating it), so it isn't included until a
working build is confirmed elsewhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import OgunCfg

try:
    from rocketpy import Environment, Flight, GenericMotor, Rocket
except ImportError:  # pragma: no cover - exercised via the ok=False path
    Environment = None


@dataclass
class RocketFlightResult:
    ok: bool
    error: str = ""
    apogee_m: float = 0.0
    max_speed_ms: float = 0.0
    max_acceleration_ms2: float = 0.0
    time_to_apogee_s: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class AerospaceLab:
    def __init__(self, cfg: OgunCfg):
        self.cfg = cfg

    def rocket_flight(
        self,
        total_impulse_ns: float,
        burn_time_s: float,
        propellant_mass_kg: float,
        rocket_dry_mass_kg: float,
        rocket_radius_m: float,
        motor_dry_mass_kg: float = 1.0,
        drag_coefficient: float = 0.5,
        nose_length_m: float | None = None,
        fin_count: int = 4,
        fin_root_chord_m: float | None = None,
        fin_tip_chord_m: float | None = None,
        fin_span_m: float | None = None,
        rail_length_m: float = 2.0,
        inclination_deg: float = 85.0,
    ) -> RocketFlightResult:
        if not self.cfg.enabled:
            return RocketFlightResult(ok=False, error="Ogun 3D disabled on this node (set ogun.enabled: true)")
        if Environment is None:
            return RocketFlightResult(ok=False, error="rocketpy not installed (pip install 'boddos[ogun]')")
        if burn_time_s <= 0 or total_impulse_ns <= 0:
            return RocketFlightResult(ok=False, error="total_impulse_ns and burn_time_s must be positive")
        if rocket_radius_m <= 0:
            return RocketFlightResult(ok=False, error="rocket_radius_m must be positive")

        # Sane geometric defaults scaled off the body radius when not given —
        # a typical small/mid-power rocket's proportions.
        nose_length_m = nose_length_m or rocket_radius_m * 5
        fin_root_chord_m = fin_root_chord_m or rocket_radius_m * 2
        fin_tip_chord_m = fin_tip_chord_m or rocket_radius_m * 0.75
        fin_span_m = fin_span_m or rocket_radius_m * 2

        warnings: list[str] = []
        try:
            env = Environment(latitude=0, longitude=0, elevation=0)
            env.set_atmospheric_model(type="standard_atmosphere")

            avg_thrust = total_impulse_ns / burn_time_s
            motor = GenericMotor(
                thrust_source=avg_thrust,
                burn_time=burn_time_s,
                chamber_radius=rocket_radius_m * 0.8,
                chamber_height=fin_root_chord_m,
                chamber_position=-0.3,
                propellant_initial_mass=propellant_mass_kg,
                nozzle_radius=rocket_radius_m * 0.3,
                dry_mass=motor_dry_mass_kg,
                dry_inertia=(0.1, 0.1, 0.01),
            )

            rocket = Rocket(
                radius=rocket_radius_m,
                mass=rocket_dry_mass_kg,
                inertia=(rocket_dry_mass_kg, rocket_dry_mass_kg, rocket_dry_mass_kg * 0.01),
                power_off_drag=drag_coefficient,
                power_on_drag=drag_coefficient,
                center_of_mass_without_motor=0,
                coordinate_system_orientation="tail_to_nose",
            )
            rocket.add_motor(motor, position=-0.3)
            rocket.set_rail_buttons(0.1, -0.1)
            rocket.add_nose(length=nose_length_m, kind="vonKarman", position=nose_length_m + 0.4)
            rocket.add_trapezoidal_fins(
                n=fin_count, root_chord=fin_root_chord_m, tip_chord=fin_tip_chord_m,
                span=fin_span_m, position=-0.25,
            )
            rocket.add_parachute(
                name="main", cd_s=1.5, trigger="apogee", sampling_rate=105, lag=1.0, noise=(0, 8.3, 0.5),
            )

            static_margin = rocket.static_margin(0)
            if static_margin < 1.0:
                warnings.append(
                    f"static margin is {static_margin:.2f} cal at liftoff (want 1-2) — "
                    "this geometry is not aerodynamically stable; move the fins aft, enlarge "
                    "them, or lengthen the nose before trusting this trajectory"
                )

            flight = Flight(
                rocket=rocket, environment=env, rail_length=rail_length_m,
                inclination=inclination_deg, heading=0, verbose=False,
            )
        except Exception as e:
            return RocketFlightResult(ok=False, error=f"simulation failed: {e}")

        if flight.max_speed > 340:
            warnings.append("max speed exceeds Mach 1 — transonic effects make this drag model unreliable")
        if flight.out_of_rail_velocity < 15:
            warnings.append("rail-exit velocity is low (<15 m/s) — the rocket may not be stable leaving the rail")

        return RocketFlightResult(
            ok=True,
            apogee_m=flight.apogee - env.elevation,
            max_speed_ms=flight.max_speed,
            max_acceleration_ms2=flight.max_acceleration,
            time_to_apogee_s=flight.apogee_time,
            warnings=warnings,
        )
