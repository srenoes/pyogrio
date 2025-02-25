import os
import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

from pyogrio import list_layers
from pyogrio.geopandas import read_dataframe, write_dataframe

try:
    import geopandas as gp
    from geopandas.testing import assert_geodataframe_equal
    has_geopandas = True
except ImportError:
    has_geopandas = False


pytestmark = pytest.mark.skipif(not has_geopandas, reason="GeoPandas not available")


def test_read_dataframe(naturalearth_lowres):
    df = read_dataframe(naturalearth_lowres)

    assert isinstance(df, gp.GeoDataFrame)

    assert df.crs == "EPSG:4326"
    assert len(df) == 177
    assert df.columns.tolist() == [
        "pop_est",
        "continent",
        "name",
        "iso_a3",
        "gdp_md_est",
        "geometry",
    ]

    assert df.geometry.iloc[0].type == "MultiPolygon"


def test_read_dataframe_vsi(naturalearth_lowres_vsi):
    df = read_dataframe(naturalearth_lowres_vsi)
    assert len(df) == 177


def test_read_no_geometry(naturalearth_lowres):
    df = read_dataframe(naturalearth_lowres, read_geometry=False)
    assert isinstance(df, pd.DataFrame)
    assert not isinstance(df, gp.GeoDataFrame)


def test_read_force_2d(test_fgdb_vsi):
    with pytest.warns(
        UserWarning, match=r"Measured \(M\) geometry types are not supported"
    ):
        df = read_dataframe(test_fgdb_vsi, layer="test_lines", max_features=1)
        assert df.iloc[0].geometry.has_z

        df = read_dataframe(
            test_fgdb_vsi, layer="test_lines", force_2d=True, max_features=1
        )
        assert not df.iloc[0].geometry.has_z


@pytest.mark.filterwarnings("ignore: Measured")
def test_read_layer(test_fgdb_vsi):
    layers = list_layers(test_fgdb_vsi)
    # The first layer is read by default (NOTE: first layer has no features)
    df = read_dataframe(test_fgdb_vsi, read_geometry=False, max_features=1)
    df2 = read_dataframe(
        test_fgdb_vsi, layer=layers[0][0], read_geometry=False, max_features=1
    )
    assert_frame_equal(df, df2)

    # Reading a specific layer should return that layer.
    # Detected here by a known column.
    df = read_dataframe(
        test_fgdb_vsi, layer="test_lines", read_geometry=False, max_features=1
    )
    assert "RIVER_MILE" in df.columns


@pytest.mark.filterwarnings("ignore: Measured")
def test_read_datetime(test_fgdb_vsi):
    df = read_dataframe(test_fgdb_vsi, layer="test_lines", max_features=1)
    assert df.SURVEY_DAT.dtype.name == "datetime64[ns]"


def test_read_null_values(test_fgdb_vsi):
    df = read_dataframe(test_fgdb_vsi, read_geometry=False)

    # make sure that Null values are preserved
    assert df.SEGMENT_NAME.isnull().max() == True
    assert df.loc[df.SEGMENT_NAME.isnull()].SEGMENT_NAME.iloc[0] == None


@pytest.mark.filterwarnings("ignore: Layer")
def test_read_where(naturalearth_lowres):
    # empty filter should return full set of records
    df = read_dataframe(naturalearth_lowres, where="")
    assert len(df) == 177

    # should return singular item
    df = read_dataframe(naturalearth_lowres, where="iso_a3 = 'CAN'")
    assert len(df) == 1
    assert df.iloc[0].iso_a3 == "CAN"

    df = read_dataframe(naturalearth_lowres, where="iso_a3 IN ('CAN', 'USA', 'MEX')")
    assert len(df) == 3
    assert len(set(df.iso_a3.unique()).difference(["CAN", "USA", "MEX"])) == 0

    # should return items within range
    df = read_dataframe(
        naturalearth_lowres, where="POP_EST >= 10000000 AND POP_EST < 100000000"
    )
    assert len(df) == 75
    assert df.pop_est.min() >= 10000000
    assert df.pop_est.max() < 100000000

    # should match no items
    df = read_dataframe(naturalearth_lowres, where="ISO_A3 = 'INVALID'")
    assert len(df) == 0


def test_read_where_invalid(naturalearth_lowres):
    with pytest.raises(ValueError, match="Invalid SQL"):
        read_dataframe(naturalearth_lowres, where="invalid")


@pytest.mark.parametrize(
    "driver,ext",
    [
        ("ESRI Shapefile", "shp"),
        ("GeoJSON", "geojson"),
        ("GeoJSONSeq", "geojsons"),
        ("GPKG", "gpkg"),
    ],
)
def test_write_dataframe(tmpdir, naturalearth_lowres, driver, ext):
    expected = read_dataframe(naturalearth_lowres)

    filename = os.path.join(str(tmpdir), f"test.{ext}")
    write_dataframe(expected, filename, driver=driver)

    assert os.path.exists(filename)

    df = read_dataframe(filename)

    if driver != "GeoJSONSeq":
        # GeoJSONSeq driver I/O reorders features and / or vertices, and does
        # not support roundtrip comparison

        # Coordinates are not precisely equal when written to JSON
        # dtypes do not necessarily round-trip precisely through JSON
        is_json = driver == "GeoJSON"

        assert_geodataframe_equal(
            df, expected, check_less_precise=is_json, check_dtype=not is_json
        )

