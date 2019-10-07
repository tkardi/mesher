# -*- coding: utf-8 -*-

import fiona as fio
import hashlib
import json
import logging

from rtree import index

from shapely.geometry import shape, LineString, Point
from shapely.ops import unary_union, linemerge

logger = logging.getLogger("mesher")


class Builder(object):
    def __init__(self):
        self.rings = {}
        self.merged = {}
        self.index = index.Index()

    def load(self, fp, encoding='utf-8'):
        """Load data using fiona and build RTree spatial index along the way.

        Many different files can be loaded (e.g diff countries). But NB! no
        topological correctness is currently checked nor enforced, no snapping
        takes place, and data from different files is expected to be using the
        same coordinate reference system.
        """
        idx = 0
        with fio.open(fp, encoding=encoding) as src:
            logger.debug('Load start: %s' % (fp, ))
            for i, feature in enumerate(src):
#                # test for a specific subregion only
#                if feature['properties']['OKOOD'] != '0214':
#                    continue
                s = shape(feature['geometry'])
                for geom in self._dump(s):
                    for ring in self._dump_rings(geom):
                        self.rings[idx] = ring
                        self.index.insert(
                            idx,
                            ring.bounds,
                            obj=dict(
                                id=idx,
                                properties=feature['properties'],
                                geometry=geom
                            )
                        )
                        idx += 1
        logger.debug('Load done: %s. Loaded %s rings' % (fp, idx))

    def build_linework(self, propertyname):
        logger.info('build_linework start')
        for idx, ring in self.rings.items():
            logger.debug('build_linework start: %s' % (idx, ))
            # walk all extracted rings and find others that intersect
            others = [f for f in self._intersects(ring)]
            if len(others) == 1 and others[0]['id'] == idx:
                # if only one other was found and the other is actually self
                c = self._get_center(ring)
                hash = self._get_md5_hash(c.wkt.encode('utf-8'))
                logger.debug('build_linework: %s. NO OTHERS FOUND, get sidedness' % (idx, ))
                props = self._get_left_right(hash, ring, propertyname)
                props['idx'] = idx
                self.merged[hash] = {'geometry':LineString(ring), 'properties':props}
                #logger.debug('%s get sidedness DONE' % (idx, ))
            else:
                # found multiple others, union
                rings_to_merge = [self.rings[id] for id in [f['id'] for f in others]]
                lines_to_merge = [line for line in self._dump(unary_union(rings_to_merge))]
                merged = self._linemerge(lines_to_merge)
                logger.debug('build_linework: %s. OTHERS FOUND, merging' % (idx, ))
                for meshline in merged:
                    center_point = self._get_center(meshline)
                    hash = self._get_md5_hash(center_point.wkt.encode('utf-8'))
                    if hash not in self.merged and ring.intersects(center_point.buffer(0.02)):
                        # only if this line is not already present
                        # and center of line must be on ring
                        first_point = Point(meshline.coords[0])
                        last_point = Point(meshline.coords[-1])
                        if ring.intersects(first_point) and ring.intersects(last_point) :
                            # only if the first and last point of line lie on ring
                            logger.debug('get sidedness idx=%s, hash=%s' % (idx, hash))
                            props = self._get_left_right(hash, meshline, propertyname)
                            props['idx'] = idx
                            self.merged[hash] = {'geometry':LineString(meshline), 'properties':props}
                            logger.debug('idx=%s, hash=%s get sidedness DONE' % (idx, hash))
            logger.debug('build_linework done: %s' % (idx, ))
        logger.info('build_linework done')

    def dump_linework(self, fp):
        """Dumps linework as a GeoJSON FeatureCollection to the specified file.
        """
        with open(fp, 'w') as dst:
            dst.write(json.dumps({"type":"FeatureCollection", "features": self.linework}))

    def _get_center(self, line):
        """Return point that lies at half-distance of line.
        """
        return line.interpolate(0.5, normalized=True)

    def _get_md5_hash(self, s):
        """Calculate a MD5 hash for a string.

        We're using the hash as an id calculated from geometry's WKT
        representation.
        """
        return hashlib.md5(s).hexdigest()

    def _get_left_right(self, hash, line, propertyname):
        """Finds what's on the left/right side of the vector.

        Initially calculated from `line.parallel_offset(0.01, 'left|right')`
        but for costlines this is a very tedious operation. So instead it's
        calculated through sampling a segment from the input line at
        half-distance of the input line.

        Returns a dict of hash, and left-right properties.
        """
        center_sample = self._line_center_sample(line)
        #logger.debug('get left parallel offset %s' % (hash, ) )
        left = self._get_center(center_sample.parallel_offset(0.01, 'left'))
        #logger.debug('done left parallel offset %s' % (hash, ) )
        #logger.debug('get right parallel offset %s' % (hash, ) )
        right = self._get_center(center_sample.parallel_offset(0.01, 'right'))
        #logger.debug('done right parallel offset %s' % (hash, ) )
        return {
            'hash' : hash,
            'left_%s' % (propertyname.lower(), ) : self._get_side(left, propertyname),
            'right_%s' % (propertyname.lower(), ) : self._get_side(right, propertyname)
        }

    def _line_center_sample(self, line):
        """Sample a input linestring at it's half-distance.

        Returns a two-coordinate LineString in the same coordinate order as
        the input line. The linestring is constructed as [coords[i-1], coords[i]]
        where `i` is the 0-based vertex index where the half-distance of input line
        is surpassed. So `i` must reference at least the 2nd coordinate-pair
        (or any other until and icluding the last).
        """
        half_distance = line.length / 2
        coords = list(line.coords)
        if len(coords) == 2:
            return line
        for i, p in enumerate(coords):
            point_distance = line.project(Point(p))
            if point_distance > half_distance:
                return LineString([coords[i-1], coords[i]])

    def _get_side(self, pnt, propertyname):
        """Gets the requested property of the polygon the input point falls in.
        """
        try:
            #logger.debug('get intersection for %s' % (hash, ) )
            feature = [f for f in self._intersects(pnt)][0]
            #logger.debug('done intersection for %s' % (hash, ) )
            return feature['properties'][propertyname]
        except IndexError as ie:
            #logger.debug('done intersection for %s, NONE' % (hash, ) )
            return None

    def _intersects(self, obj):
        """RTree index lookup + verification.
        """
        for f in self.index.intersection(obj.bounds, objects="raw"):
            if obj.intersects(f['geometry']):
                yield f

    def _linemerge(self, lines_to_merge):
        """Performs a linemerge operation on a list of lines.
        """
        try:
            for line in linemerge(lines_to_merge).geoms:
                yield line
        except AttributeError as ae:
            yield linemerge(lines_to_merge)

    def _dump(self, shape):
        """Dumps multipart geometries to singleparts.

        Think of this as SQL's `st_dump(geometry)`.
        """
        if hasattr(shape, 'geoms'):
            for geom in shape.geoms:
                yield geom
        else:
            yield shape

    def _dump_rings(self, geom):
        """Dumps polygon's component rings as LinearRings.
        """
        yield geom.exterior
        for interior in geom.interiors:
            yield interior

    @property
    def linework(self):
        """Return a list of GeoJSON features of built line-mesh.
        """
        return [
            dict(
                type="Feature",
                id=hash,
                geometry=linemesh['geometry'].__geo_interface__,
                properties=linemesh['properties']
            ) for hash, linemesh in self.merged.items()]
