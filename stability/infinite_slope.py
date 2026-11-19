"""Uniform infinite-slope reference model; SI stresses in kPa, angles in degrees."""
import math


class ModelDomainError(ValueError):
    pass


def factor_of_safety(cohesion_kpa, friction_deg, unit_weight_kn_m3,
                     slope_deg, failure_depth_m, pressure_head_m):
    """Vertical failure depth, slope-parallel plane, atmospheric air pressure.

    Negative water head contributes no suction strength. No seismic load, roots,
    deformation, erosion, or strength degradation is represented.
    """
    values = (cohesion_kpa, friction_deg, unit_weight_kn_m3, slope_deg,
              failure_depth_m, pressure_head_m)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in values):
        raise ValueError('All model inputs must be finite numbers.')
    if cohesion_kpa < 0 or not 0 < friction_deg < 90:
        raise ValueError('Cohesion must be nonnegative; friction angle must be between 0 and 90 degrees.')
    if unit_weight_kn_m3 <= 0 or failure_depth_m <= 0 or not 0 < slope_deg < 90:
        raise ValueError('Weight and depth must be positive; slope angle must be between 0 and 90 degrees.')
    beta = math.radians(slope_deg)
    normal = unit_weight_kn_m3 * failure_depth_m * math.cos(beta) ** 2
    pore = 9.81 * max(pressure_head_m, 0)
    effective = normal - pore
    if effective < 0:
        raise ModelDomainError('Pore pressure exceeds total normal stress; the frictional contact model is outside its valid domain.')
    driving = unit_weight_kn_m3 * failure_depth_m * math.sin(beta) * math.cos(beta)
    return (cohesion_kpa + effective * math.tan(math.radians(friction_deg))) / driving
