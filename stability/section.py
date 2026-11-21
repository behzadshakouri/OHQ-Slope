"""One-way transfer of native OHQ pressures to a fixed circular slip surface."""
from dataclasses import replace
import math

from hydrology.column import interpolate
from hydrology.native_grid import sample_at_probe
from stability.bishop import Slice, factor_of_safety


def fixed_surface_history(run, slices, base_points, water_unit_weight_kn_m3=9.807):
    """Keep slice geometry, strengths and weights fixed at each saved OHQ time."""
    if not math.isfinite(water_unit_weight_kn_m3) or water_unit_weight_kn_m3 <= 0:
        raise ValueError('Water unit weight must be positive and finite.')
    if not slices or len(slices) != len(base_points):
        raise ValueError('Provide one basal pressure sampling point per slice.')
    pressure = [sample_at_probe(run,x,y,include_boundary_cells=True) for x,y in base_points]
    history = []
    for rows in zip(*pressure, strict=True):
        pressure_kpa = [row['pressure_head_m']*water_unit_weight_kn_m3 for row in rows]
        parts = [replace(part,pressure_kpa=u) for part,u in zip(slices,pressure_kpa,strict=True)]
        history.append({'time_h':rows[0]['time_h'],'pressure_kpa':pressure_kpa,
                        'factor_of_safety':factor_of_safety(parts)})
    return history


def circular_slices(ground, entry_x, exit_x, sagitta_m, count,
                    unit_weight, cohesion, friction_rad, suction_friction_rad=0.):
    """Build a lower circular arc between two ground intersections and slice it vertically."""
    if (len(ground) < 2 or any(a[0] >= b[0] for a,b in zip(ground,ground[1:]))
            or not ground[0][0] <= entry_x < exit_x <= ground[-1][0]
            or type(count) is not int or count < 2 or not math.isfinite(unit_weight) or unit_weight <= 0):
        raise ValueError('Invalid ground intersection, slice count, or unit weight.')
    y0, y1 = interpolate(ground,entry_x), interpolate(ground,exit_x)
    dx, dy = exit_x-entry_x, y1-y0
    chord = math.hypot(dx,dy)
    if not 0 < sagitta_m < chord/2:
        raise ValueError('Sagitta must be positive and smaller than half the chord.')
    radius = chord**2/(8*sagitta_m)+sagitta_m/2
    offset = radius-sagitta_m
    cx = (entry_x+exit_x)/2-dy*offset/chord
    cy = (y0+y1)/2+dx*offset/chord
    if cy <= max(y0,y1):
        raise ValueError('The candidate extends beyond the lower circular branch.')

    def base(x):
        vertical = math.sqrt(max(0.,radius**2-(x-cx)**2))
        return cy-vertical

    # Between ground vertices the base is convex, so checking the vertices
    # also checks that the base does not protrude above the linear ground.
    interior = [x for x,_ in ground if entry_x < x < exit_x]
    if any(base(x) > interpolate(ground,x)+1e-10 for x in interior):
        raise ValueError('The candidate passes above the ground surface.')

    width = dx/count
    slices, points = [], []
    for i in range(count):
        x = entry_x+(i+.5)*width
        elevation = base(x)
        thickness = interpolate(ground,x)-elevation
        if thickness <= 0:
            raise ValueError('A slice has no soil above its base.')
        angle = math.atan2(cx-x,cy-elevation)
        slices.append(Slice(width,width*thickness*unit_weight,angle,cohesion,friction_rad,
                            0.,suction_friction_rad))
        points.append((x,elevation))
    return slices, points


def screen_circular_surfaces(run, ground, candidates, count, unit_weight, cohesion,
                             friction_rad, suction_friction_rad=0.):
    """Find the minimum over an explicit candidate set at each saved time."""
    accepted, rejected = [], []
    for candidate in candidates:
        try:
            slices, points = circular_slices(ground,*candidate,count,unit_weight,cohesion,
                                             friction_rad,suction_friction_rad)
            history = fixed_surface_history(run,slices,points)
        except ValueError as error:
            rejected.append({'candidate':candidate,'reason':str(error)})
            continue
        accepted.append({'candidate':candidate,
                         'history':[{'time_h':row['time_h'],'factor_of_safety':row['factor_of_safety']}
                                    for row in history]})
    if not accepted:
        raise ValueError('No candidate circle can be evaluated on this seepage grid.')
    envelope = []
    for index, row in enumerate(accepted[0]['history']):
        critical = min(accepted,key=lambda trial:trial['history'][index]['factor_of_safety'])
        envelope.append({**row,'factor_of_safety':critical['history'][index]['factor_of_safety'],
                         'candidate':critical['candidate']})
    return {'accepted':accepted,'rejected':rejected,'envelope':envelope}
