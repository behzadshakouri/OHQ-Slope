"""Simplified Bishop for prescribed circular slices under static vertical loading."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Slice:
    width_m: float
    weight_kn_m: float
    downslope_angle_rad: float
    cohesion_kpa: float
    friction_rad: float
    pressure_kpa: float
    suction_friction_rad: float = 0.


def factor_of_safety(slices):
    """Solve Bishop equilibrium per metre out of plane, with optional constant phi-b suction strength."""
    terms = []
    for part in slices:
        b, w, angle = part.width_m, part.weight_kn_m, part.downslope_angle_rad
        c, phi, u = part.cohesion_kpa, part.friction_rad, part.pressure_kpa
        phi_b = part.suction_friction_rad
        if (not all(map(math.isfinite,(b,w,angle,c,phi,u,phi_b))) or b <= 0 or w <= 0
                or abs(angle) >= math.pi/2 or c < 0 or not 0 <= phi < math.pi/2
                or not 0 <= phi_b < math.pi/2):
            raise ValueError('Invalid geometry or strength for a Bishop slice.')
        sin, cos, tan_phi = math.sin(angle), math.cos(angle), math.tan(phi)
        suction_cohesion = max(0.,-u)*math.tan(phi_b)
        resistance = (c+suction_cohesion)*b + (w-max(0.,u)*b)*tan_phi
        if resistance < 0:
            raise ValueError('A slice has negative resistance under the prescribed pressure.')
        terms.append((w*sin,cos,sin*tan_phi,resistance))
    driving = math.fsum(term[0] for term in terms)
    if driving <= 0:
        raise ValueError('The prescribed slip direction has no positive driving force.')

    # Divide the usual Bishop equation by F, yielding a decreasing residual.
    singular = max(0., *(-sin_phi/cos for _,cos,sin_phi,_ in terms))

    def residual(factor):
        return math.fsum(resistance/(factor*cos+sin_phi)
                         for _,cos,sin_phi,resistance in terms) - driving

    low = singular+1e-12*max(1.,singular)
    if residual(low) <= 0:
        raise ValueError('No positive Bishop root with admissible slice denominators.')
    high = max(1.,2*low)
    while residual(high) > 0:
        high *= 2
        if not math.isfinite(high):
            raise ValueError('Unable to bracket the Bishop factor of safety.')
    for _ in range(80):
        middle = (low+high)/2
        if residual(middle) > 0:
            low = middle
        else:
            high = middle
    return (low+high)/2
