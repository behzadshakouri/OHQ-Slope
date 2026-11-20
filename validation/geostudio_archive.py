"""Read selected saved GeoStudio pressure/graph series without running GeoStudio."""
import csv
import io
import math
import struct
import xml.etree.ElementTree as ET
import zipfile


def csv_rows(archive,member):
    return list(csv.DictReader(io.StringIO(archive.read(member).decode('utf-8-sig'))))


def mesh_nodes(data):
    header,body=data.split(b'end_header\n',1)
    text=header.decode()
    if 'format binary_little_endian 1.0' not in text:
        raise ValueError('Expected supported little-endian PLY mesh.')
    # Require the actual layout, rather than guessing offsets from an arbitrary PLY.
    lines=text.splitlines();i=lines.index('element version 1')
    if lines[i+1:i+3]!=['property ushort major','property ushort minor']:raise ValueError('Unsupported PLY version layout.')
    line=next(line for line in lines if line.startswith('element node '));n=int(line.split()[-1]);j=lines.index(line)
    if lines[j+1:j+4]!=['property double x','property double y','property double z']:raise ValueError('Unsupported PLY coordinate layout.')
    if len(body)<4+24*n:raise ValueError('Truncated mesh node data.')
    return {k+1:struct.unpack_from('<ddd',body,4+24*k)[:2] for k in range(n)}


def graph_location(xml,member):
    graph_id=int(member.rsplit('/',1)[-1].split('_')[1])
    root=ET.fromstring(xml)
    graphs=[g for g in root.iter('ResultGraph') if g.find('CacheId') is not None and int(g.find('CacheId').get('ID'))==graph_id]
    if len(graphs)!=1:raise ValueError('Graph identity missing or ambiguous in saved snapshot.')
    graph=graphs[0]
    sequence=int(member.rsplit('/',1)[-1].rsplit('.',1)[0].split('_')[2])
    if int(graph.find('CacheId').get('CacheSequenceNumber','-1'))!=sequence:
        raise ValueError('Cached graph sequence differs from saved snapshot.')
    use=next(u for u in root.iter('UsesLocation') if u.get('ID')==f'ResultGraphs-{graph_id}')
    loc=next(l for l in root.iter('Location') if l.findtext('ID')==use.get('Entry'))
    source=loc.findtext('Sources/ID')
    if not source or not source.startswith('CutLines-'):raise ValueError('Expected a point cut-line graph location.')
    cut=next(c for c in root.iter('CutLine') if c.findtext('ID')==source.split('-')[1])
    points=cut.findall('Points/Point')
    if len(points)!=1 or graph.findtext('X')!='Time':raise ValueError('Expected a time graph at a single coordinate.')
    return {'x_m':float(points[0].get('X')),'y_m':float(points[0].get('Y')),
            'quantity':graph.findtext('Y'),'graph_id':graph_id,'cache_sequence':sequence,'location_id':int(use.get('Entry'))}


def extract(path,analysis,points):
    result={}
    with zipfile.ZipFile(path) as archive:
        xmls=[n for n in archive.namelist() if n.startswith(analysis+'/') and n.count('/')==1 and n.endswith('.xml')]
        if len(xmls)!=1:raise ValueError('Expected one saved analysis XML snapshot.')
        xml=archive.read(xmls[0]);nodes=mesh_nodes(archive.read(analysis+'/Mesh.ply'))
        steps=csv_rows(archive,analysis+'/time.csv')
        if not steps:raise ValueError('No saved analysis times.')
        for point in points:
            entry={'point':point,'reference_role':'Archived numerical model, not experimental observations'}
            if 'archive_node' in point:
                node=point['archive_node'];position=nodes[node];series=[]
                for step in steps:
                    member=f"{analysis}/{int(step['Step']):03d}/node.csv"
                    rows=csv_rows(archive,member)
                    matches=[r for r in rows if int(r['Node'])==node]
                    if len(matches)!=1:raise ValueError('Missing or duplicate requested mesh node.')
                    pressure=float(matches[0]['PoreWaterPressure'])
                    series.append({'time_h':float(step['Time'])/3600,'pressure_kpa':pressure,'pressure_head_m':pressure/9.807})
                entry.update(series=series,node_id=node,node_position_m=list(position),
                             coordinate_distance_m=math.hypot(position[0]-point['x_m'],position[1]-point['y_m']),
                             source=f'{analysis}/NNN/node.csv')
            elif 'archive_theta_graph' in point:
                member=point['archive_theta_graph'];loc=graph_location(xml,member)
                if loc['quantity']!='VolWaterContent' or abs(loc['x_m']-point['x_m'])>1e-10 or abs(loc['y_m']-point['y_m'])>1e-10:
                    raise ValueError('Cached moisture graph does not match requested coordinate/quantity.')
                series=[{'time_h':float(r['Time'])/3600,'theta':float(r['VolWaterContent'])} for r in csv_rows(archive,member)]
                entry.update(series=series,source=member,graph_location=loc,snapshot_member=xmls[0])
            else:raise ValueError('Specify an archive mesh node or verified moisture graph.')
            if len(entry['series'])!=len(steps) or any(abs(r['time_h']-float(s['Time'])/3600)>1e-9 for r,s in zip(entry['series'],steps)):
                raise ValueError('Reference series differs from saved analysis time grid.')
            if any(not all(math.isfinite(v) for v in row.values()) for row in entry['series']):raise ValueError('Nonfinite archived values.')
            result[point['id']]=entry
    return result
