"""Cell-centred 2D saturated seepage on a rectangular grid of unit width."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Grid:
    width_m: float
    height_m: float
    nx: int
    nz: int

    def __post_init__(self):
        if any(not math.isfinite(d) or d <= 0 for d in (self.width_m, self.height_m)):
            raise ValueError('Grid dimensions must be finite and positive.')
        if any(type(n) is not int or n < 1 for n in (self.nx, self.nz)):
            raise ValueError('Cell counts must be positive integers.')

    @property
    def dx(self):
        return self.width_m / self.nx

    @property
    def dz(self):
        return self.height_m / self.nz


def _solve(diagonal, neighbors, rhs):
    """Jacobi-preconditioned conjugate gradient for the finite-volume system."""
    def multiply(vector):
        return [d * vector[i] - sum(weight * vector[j] for j, weight in row)
                for i, (d, row) in enumerate(zip(diagonal, neighbors))]

    def dot(a, b):
        return math.fsum(x * y for x, y in zip(a, b))

    x = [0.] * len(rhs)
    residual = list(rhs)
    scaled = [r / d for r, d in zip(residual, diagonal)]
    direction = scaled.copy()
    energy = dot(residual, scaled)
    tolerance = 1e-12 * max(map(abs, rhs))
    for _ in range(len(rhs)):
        if max(map(abs, residual)) <= tolerance:
            return x
        product = multiply(direction)
        step = energy / dot(direction, product)
        x = [value + step * delta for value, delta in zip(x, direction)]
        residual = [value - step * delta for value, delta in zip(residual, product)]
        scaled = [r / d for r, d in zip(residual, diagonal)]
        new_energy = dot(residual, scaled)
        direction = [value + new_energy / energy * previous
                     for value, previous in zip(scaled, direction)]
        energy = new_energy
    if max(map(abs, residual)) <= tolerance:
        return x
    raise ValueError('The 2D seepage linear solve did not converge.')


def steady_seepage(grid, conductivity_x_m_h, conductivity_z_m_h, boundary_heads_m):
    """Solve total head with prescribed face heads and zero flux elsewhere.

    Prescribed heads are sequences ordered bottom to top on left/right faces
    and left to right on bottom/top faces. Head and pressure are returned in
    rows from the base upward, with x varying within each row. Darcy fluxes
    are positive along the corresponding coordinate axis.
    """
    face_sizes = {'left': grid.nz, 'right': grid.nz, 'bottom': grid.nx, 'top': grid.nx}
    if not boundary_heads_m or set(boundary_heads_m) - face_sizes.keys():
        raise ValueError('Specify heads on at least one of left, right, bottom or top.')
    for side, heads in boundary_heads_m.items():
        if len(heads) != face_sizes[side] or not all(map(math.isfinite, heads)):
            raise ValueError(f'Expected one finite head per {side} boundary face.')

    return _seepage(grid, conductivity_x_m_h, conductivity_z_m_h, boundary_heads_m)


def transient_step(grid, conductivity_x_m_h, conductivity_z_m_h, previous_head_m,
                   specific_storage_per_m, step_h, rainfall_m_h, right_seepage_faces):
    """Advance saturated storage under imposed infiltration and a one-way right outlet."""
    if (len(previous_head_m) != grid.nz
            or any(len(row) != grid.nx or not all(map(math.isfinite, row)) for row in previous_head_m)):
        raise ValueError('Initial total heads must be finite and match the grid.')
    if any(not math.isfinite(v) or v <= 0 for v in (specific_storage_per_m, step_h)):
        raise ValueError('Specific storage and time step must be finite and positive.')
    if not math.isfinite(rainfall_m_h) or rainfall_m_h < 0:
        raise ValueError('Rainfall must be finite and nonnegative.')
    candidates = set(right_seepage_faces)
    if any(type(j) is not int or not 0 <= j < grid.nz for j in candidates):
        raise ValueError('Seepage faces must be valid right-boundary row indices.')

    elevation = [(j + .5) * grid.dz for j in range(grid.nz)]
    if any(h < z - 1e-10 for z, row in zip(elevation, previous_head_m) for h in row):
        raise ValueError('Initial pressure must be nonnegative for this saturated model.')
    active = {j for j in candidates if previous_head_m[j][-1] > elevation[j]}
    previous = [value for row in previous_head_m for value in row]
    storage_rate_coefficient = specific_storage_per_m * grid.dx * grid.dz / step_h
    visited = set()
    for _ in range(2 * len(candidates) + 2):
        signature = frozenset(active)
        if signature in visited:
            raise ValueError('The seepage-face active set cycled.')
        visited.add(signature)
        heads = {'right': [z if j in active else None for j, z in enumerate(elevation)]}
        result = _seepage(grid, conductivity_x_m_h, conductivity_z_m_h, heads,
                          rainfall_m_h=rainfall_m_h, storage_rate_coefficient=storage_rate_coefficient,
                          previous=previous)
        updated = {j for j in candidates if result['total_head_m'][j][-1] > elevation[j]}
        if active == updated:
            if any(psi < -1e-10 for row in result['pressure_head_m'] for psi in row):
                raise ValueError('The saturated transient model encountered negative pressure.')
            return dict(result, active_right_seepage_faces=sorted(active),
                        rainfall_m_h=rainfall_m_h, step_h=step_h)
        active = updated
    raise ValueError('The seepage-face active set did not converge.')


def _seepage(grid, kx, kz, boundary_heads_m, *, rainfall_m_h=0.,
             storage_rate_coefficient=0., previous=None):
    if any(not math.isfinite(k) or k <= 0 for k in (kx, kz)):
        raise ValueError('Conductivities must be finite and positive.')
    nx, nz, dx, dz = grid.nx, grid.nz, grid.dx, grid.dz
    gx, gz = kx * dz / dx, kz * dx / dz
    diagonal, neighbors, rhs = [], [], []
    for iz in range(nz):
        for ix in range(nx):
            cell = iz * nx + ix
            row, boundary_diagonal, forcing = [], 0., 0.
            faces = (
                ('left', ix > 0, cell - 1, iz, gx),
                ('right', ix + 1 < nx, cell + 1, iz, gx),
                ('bottom', iz > 0, cell - nx, ix, gz),
                ('top', iz + 1 < nz, cell + nx, ix, gz),
            )
            for side, interior, neighbor, index, weight in faces:
                if interior:
                    row.append((neighbor, weight))
                elif side in boundary_heads_m and boundary_heads_m[side][index] is not None:
                    boundary_diagonal += 2 * weight
                    forcing += 2 * weight * boundary_heads_m[side][index]
            if iz + 1 == nz:
                forcing += rainfall_m_h * dx
            if previous is not None:
                boundary_diagonal += storage_rate_coefficient
                forcing += storage_rate_coefficient * previous[cell]
            neighbors.append(row)
            diagonal.append(boundary_diagonal + sum(weight for _, weight in row))
            rhs.append(forcing)

    flat_head = _solve(diagonal, neighbors, rhs)
    head = [flat_head[start:start + nx] for start in range(0, len(flat_head), nx)]
    x = [(i + .5) * dx for i in range(nx)]
    z = [(i + .5) * dz for i in range(nz)]

    def edge_flux(side, cells, conductivity, spacing, sign):
        if side not in boundary_heads_m:
            return [0.] * len(cells)
        return [0. if boundary is None else sign * 2 * conductivity * (boundary - cell) / spacing
                for cell, boundary in zip(cells, boundary_heads_m[side])]

    left = edge_flux('left', [row[0] for row in head], kx, dx, 1)
    right = edge_flux('right', [row[-1] for row in head], kx, dx, -1)
    bottom = edge_flux('bottom', head[0], kz, dz, 1)
    top = (edge_flux('top', head[-1], kz, dz, -1) if 'top' in boundary_heads_m
           else [-rainfall_m_h] * nx)
    flux_x = [[left[j], *(-kx * (b - a) / dx for a, b in zip(row, row[1:])), right[j]]
              for j, row in enumerate(head)]
    flux_z = [bottom, *([-kz * (b - a) / dz for a, b in zip(lower, upper)]
                       for lower, upper in zip(head, head[1:])), top]
    outflow = {'left': -math.fsum(left) * dz, 'right': math.fsum(right) * dz,
               'bottom': -math.fsum(bottom) * dx, 'top': math.fsum(top) * dx}
    storage = [0.] * len(flat_head) if previous is None else [
        storage_rate_coefficient * (current - old) for current, old in zip(flat_head, previous)]
    net_outflow = math.fsum(outflow.values())
    storage_rate = math.fsum(storage)
    local_balance = max(abs((flux_x[j][i + 1] - flux_x[j][i]) * dz
                            + (flux_z[j + 1][i] - flux_z[j][i]) * dx + storage[j * nx + i])
                        for j in range(nz) for i in range(nx))
    return dict(x_m=x, z_m=z, total_head_m=head,
                pressure_head_m=[[value - elevation for value in row]
                                 for elevation, row in zip(z, head)],
                darcy_flux_x_m_h=flux_x, darcy_flux_z_m_h=flux_z,
                boundary_outflow_m3_h=outflow,
                net_boundary_outflow_m3_h=net_outflow, storage_change_m3_h=storage_rate,
                water_balance_residual_m3_h=net_outflow + storage_rate,
                max_cell_balance_residual_m3_h=local_balance)
