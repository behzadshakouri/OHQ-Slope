"""Interpolate saved transient SEEP/W nodal pressures on the archived mesh."""
import struct

from validation.geostudio_archive import csv_rows, mesh_nodes


def _mesh_cells(data):
    nodes = mesh_nodes(data)
    header, body = data.split(b'end_header\n', 1)
    lines = header.decode().splitlines()
    index, = [i for i, line in enumerate(lines) if line.startswith('element element ')]
    if lines[index+1:index+5] != [
        'property uchar shape_kind', 'property uchar integration_order',
        'property uint owner', 'property list uchar uint id',
    ]:
        raise ValueError('Unsupported GeoStudio element layout.')
    offset = 4 + 24*len(nodes)
    cells = []
    for _ in range(int(lines[index].split()[-1])):
        kind, _, _, count = struct.unpack_from('<BBIB', body, offset)
        ids = struct.unpack_from(f'<{count}I', body, offset+7)
        offset += 7+4*count
        if (kind, count) in ((0,1),(1,2)):
            continue
        if (kind, count) not in ((2,3),(3,4)):
            raise ValueError('Expected linear triangles and bilinear quadrilaterals.')
        coordinates = [nodes[node] for node in ids]
        xs, ys = zip(*coordinates)
        cells.append((ids, coordinates, (min(xs),max(xs),min(ys),max(ys))))
    return nodes, cells


def _solve(a,b,c,d,x,y):
    determinant = a*d-b*c
    if abs(determinant) < 1e-18:
        raise ValueError('Degenerate element in GeoStudio mesh.')
    return (d*x-b*y)/determinant, (a*y-c*x)/determinant


def _weights(points, x, y):
    x0,y0 = points[0]
    x1,y1 = points[1]
    x2,y2 = points[2]
    if len(points) == 3:
        r,s = _solve(x1-x0,x2-x0,y1-y0,y2-y0,x-x0,y-y0)
        weights = (1-r-s,r,s)
        return weights if min(weights) >= -1e-8 else None
    x3,y3 = points[3]
    a,b,c = x1-x0,x3-x0,x2-x1-x3+x0
    d,e,f = y1-y0,y3-y0,y2-y1-y3+y0
    r = s = .5
    for _ in range(20):
        ex = x-x0-a*r-b*s-c*r*s
        ey = y-y0-d*r-e*s-f*r*s
        if max(abs(ex),abs(ey)) <= 1e-11:
            if -1e-8 <= r <= 1+1e-8 and -1e-8 <= s <= 1+1e-8:
                return ((1-r)*(1-s),r*(1-s),r*s,(1-r)*s)
            return None
        dr,ds = _solve(a+c*s,b+c*r,d+f*s,e+f*r,ex,ey)
        r += dr
        s += ds
    return None


class SavedPressureField:
    def __init__(self, archive, analysis='Transient Seepage', end_h=2.):
        nodes, self.cells = _mesh_cells(archive.read(analysis+'/Mesh.ply'))
        self.frames = []
        for step in csv_rows(archive,analysis+'/time.csv'):
            t = float(step['Time'])/3600
            if t > end_h+1e-10:
                break
            rows = csv_rows(archive,f"{analysis}/{int(step['Step']):03d}/node.csv")
            pressure = {int(row['Node']):float(row['PoreWaterPressure']) for row in rows}
            if len(rows) != len(nodes) or pressure.keys() != nodes.keys():
                raise ValueError('Saved pressure records differ from the mesh nodes.')
            self.frames.append((t,pressure))
        if not self.frames:
            raise ValueError('No archived pressure frames in the requested interval.')

    def pressure_history(self, x, y):
        for ids, points, (xmin,xmax,ymin,ymax) in self.cells:
            if not (xmin-1e-10 <= x <= xmax+1e-10 and ymin-1e-10 <= y <= ymax+1e-10):
                continue
            weights = _weights(points,x,y)
            if weights is not None:
                return [{'time_h':t,'pressure_kpa':sum(p[node]*w for node,w in zip(ids,weights,strict=True))}
                        for t,p in self.frames]
        raise ValueError(f'Point ({x:g}, {y:g}) lies outside the archived seepage mesh.')
