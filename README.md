# mesher
A pythonesce approach to [Calculating a polygon mesh](https://tkardi.ee/writeup/post/2018/05/21/calculating-a-polygon-mesh/).
with left|right properties assigned to the resulting linework.

# Requires
- [shapely](https://shapely.readthedocs.io/en/stable/manual.html)
- [fiona](https://fiona.readthedocs.io/en/latest/)
- [rtree](http://toblerity.org/rtree/)

## Usage
Based on the Estonian [settlement units' data](
https://geoportaal.maaamet.ee/docs/haldus_asustus/asustusyksus_shp.zip)
downloaded from the Estonian Land Board's
[geoportal](https://geoportaal.maaamet.ee/eng/Maps-and-Data/Administrative-and-Settlement-Division-p312.html)

```
from mesher import mesher
b = mesher.Builder()
b.load(
    'data/ehak/20190901/asustusyksus_20190901.shp',
    encoding='cp1257'
)
b.build_linework('AKOOD')
b.dump_linework('data/ehak/asustusyksus_20190901.json')
```
