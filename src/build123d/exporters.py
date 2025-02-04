# pylint has trouble with the OCP imports
# pylint: disable=no-name-in-module, import-error

from build123d import *
from build123d import Shape
from OCP.GeomConvert import GeomConvert_BSplineCurveToBezierCurve  # type: ignore
from OCP.GeomConvert import GeomConvert  # type: ignore
from OCP.Geom import Geom_BSplineCurve, Geom_BezierCurve  # type: ignore
from OCP.gp import gp_XYZ, gp_Pnt, gp_Vec, gp_Dir, gp_Ax2  # type: ignore
from OCP.BRepLib import BRepLib  # type: ignore
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape  # type: ignore
from OCP.HLRAlgo import HLRAlgo_Projector  # type: ignore
from typing import Callable, List, Union, Tuple, Dict, Optional
from typing_extensions import Self
import svgpathtools as PT
import xml.etree.ElementTree as ET
from enum import Enum, auto
import ezdxf
from ezdxf import zoom
from ezdxf.math import Vec2
from ezdxf.colors import aci2rgb
from ezdxf.tools.standards import linetypes as ezdxf_linetypes
import math

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class Drawing(object):
    def __init__(
        self,
        shape: Shape,
        *,
        look_at: VectorLike = None,
        look_from: VectorLike = (1, -1, 1),
        look_up: VectorLike = (0, 0, 1),
        with_hidden: bool = True,
        focus: Union[float, None] = None,
    ):

        hlr = HLRBRep_Algo()
        hlr.Add(shape.wrapped)

        projection_origin = Vector(look_at) if look_at else shape.center()
        projection_dir = Vector(look_from).normalized()
        projection_x = Vector(look_up).normalized().cross(projection_dir)
        coordinate_system = gp_Ax2(
            projection_origin.to_pnt(), projection_dir.to_dir(), projection_x.to_dir()
        )

        if focus is not None:
            projector = HLRAlgo_Projector(coordinate_system, focus)
        else:
            projector = HLRAlgo_Projector(coordinate_system)

        hlr.Projector(projector)
        hlr.Update()
        hlr.Hide()

        hlr_shapes = HLRBRep_HLRToShape(hlr)

        visible = []

        visible_sharp_edges = hlr_shapes.VCompound()
        if not visible_sharp_edges.IsNull():
            visible.append(visible_sharp_edges)

        visible_smooth_edges = hlr_shapes.Rg1LineVCompound()
        if not visible_smooth_edges.IsNull():
            visible.append(visible_smooth_edges)

        visible_contour_edges = hlr_shapes.OutLineVCompound()
        if not visible_contour_edges.IsNull():
            visible.append(visible_contour_edges)

        hidden = []
        if with_hidden:

            hidden_sharp_edges = hlr_shapes.HCompound()
            if not hidden_sharp_edges.IsNull():
                hidden.append(hidden_sharp_edges)

            hidden_contour_edges = hlr_shapes.OutLineHCompound()
            if not hidden_contour_edges.IsNull():
                hidden.append(hidden_contour_edges)

        # magic number from CQ
        # TODO: figure out the proper source of this value.
        tolerance = 1e-6

        # Fix the underlying geometry - otherwise we will get segfaults
        for el in visible:
            BRepLib.BuildCurves3d_s(el, tolerance)
        for el in hidden:
            BRepLib.BuildCurves3d_s(el, tolerance)

        # Convert and store the results.
        self.visible_lines = Compound.make_compound(map(Shape, visible))
        self.hidden_lines = Compound.make_compound(map(Shape, hidden))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

# class AutoNameEnum(Enum):
#     def _generate_next_value_(name, start, count, last_values):
#         return name


class LineType(Enum):
    CONTINUOUS = auto()
    CENTERX2 = auto()
    CENTER2 = auto()
    DASHED = auto()
    DASHEDX2 = auto()
    DASHED2 = auto()
    PHANTOM = auto()
    PHANTOMX2 = auto()
    PHANTOM2 = auto()
    DASHDOT = auto()
    DASHDOTX2 = auto()
    DASHDOT2 = auto()
    DOT = auto()
    DOTX2 = auto()
    DOT2 = auto()
    DIVIDE = auto()
    DIVIDEX2 = auto()
    DIVIDE2 = auto()
    ISO_DASH = "ACAD_ISO02W100"  # __ __ __ __ __ __ __ __ __ __ __ __ __
    ISO_DASH_SPACE = "ACAD_ISO03W100"  # __    __    __    __    __    __
    ISO_LONG_DASH_DOT = "ACAD_ISO04W100"  # ____ . ____ . ____ . ____ . _
    ISO_LONG_DASH_DOUBLE_DOT = "ACAD_ISO05W100"  # ____ .. ____ .. ____ .
    ISO_LONG_DASH_TRIPLE_DOT = "ACAD_ISO06W100"  # ____ ... ____ ... ____
    ISO_DOT = "ACAD_ISO07W100"  # . . . . . . . . . . . . . . . . . . . .
    ISO_LONG_DASH_SHORT_DASH = "ACAD_ISO08W100"  # ____ __ ____ __ ____ _
    ISO_LONG_DASH_DOUBLE_SHORT_DASH = "ACAD_ISO09W100"  # ____ __ __ ____
    ISO_DASH_DOT = "ACAD_ISO10W100"  # __ . __ . __ . __ . __ . __ . __ .
    ISO_DOUBLE_DASH_DOT = "ACAD_ISO11W100"  # __ __ . __ __ . __ __ . __ _
    ISO_DASH_DOUBLE_DOT = "ACAD_ISO12W100"  # __ . . __ . . __ . . __ . .
    ISO_DOUBLE_DASH_DOUBLE_DOT = "ACAD_ISO13W100"  # __ __ . . __ __ . . _
    ISO_DASH_TRIPLE_DOT = "ACAD_ISO14W100"  # __ . . . __ . . . __ . . . _
    ISO_DOUBLE_DASH_TRIPLE_DOT = "ACAD_ISO15W100"  # __ __ . . . __ __ . .


class ColorIndex(Enum):
    RED = 1
    YELLOW = 2
    GREEN = 3
    CYAN = 4
    BLUE = 5
    MAGENTA = 6
    BLACK = 7
    GRAY = 8
    LIGHT_GRAY = 9


def lin_pattern(*args):
    """Convert an ISO line pattern from the values found in a standard
    AutoCAD .lin file to the values expected by ezdxf.  Specifically,
    prepend the sum of the absolute values of the lengths, and divide
    by 2.54 to convert the units from mm to 1/10in."""
    abs_args = [abs(l) for l in args]
    result = [(l / 2.54) for l in [sum(abs_args), *args]]
    return result


# Scale factor to convert various units to meters.
UNITS_PER_METER = {
    Unit.INCH: 100 / 2.54,
    Unit.FOOT: 100 / (12 * 2.54),
    Unit.MICRO: 1_000_000,
    Unit.MILLIMETER: 1000,
    Unit.CENTIMETER: 100,
    Unit.METER: 1,
}


def unit_conversion_scale(from_unit: Unit, to_unit: Unit) -> float:
    result = UNITS_PER_METER[to_unit] / UNITS_PER_METER[from_unit]
    return result


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------


class Export2D(object):
    """Base class for 2D exporters (DXF, SVG)."""

    # When specifying a parametric interval [u1, u2] on a spline,
    # OCCT considers two parameters to be equal if
    # abs(u1-u2) < tolerance, and generally raises an exception in
    # this case.
    PARAMETRIC_TOLERANCE = 1e-9

    DEFAULT_COLOR_INDEX = ColorIndex.BLACK
    DEFAULT_LINE_WEIGHT = 0.09
    DEFAULT_LINE_TYPE = LineType.CONTINUOUS

    # Pull default (ANSI) linetypes out of ezdxf for more convenient
    # lookup and add some ISO linetypes.
    LINETYPE_DEFS = {
        name: (desc, pattern) for name, desc, pattern in ezdxf_linetypes()
    } | {
        LineType.ISO_DASH.value: (
            "ISO dash __ __ __ __ __ __ __ __ __ __ __ __ __",
            lin_pattern(12, -3),
        ),
        LineType.ISO_DASH_SPACE.value: (
            "ISO dash space __    __    __    __    __    __",
            lin_pattern(12, -18),
        ),
        LineType.ISO_LONG_DASH_DOT.value: (
            "ISO long-dash dot ____ . ____ . ____ . ____ . _",
            lin_pattern(24, -3, 0, -3),
        ),
        LineType.ISO_LONG_DASH_DOUBLE_DOT.value: (
            "ISO long-dash double-dot ____ .. ____ .. ____ . ",
            lin_pattern(24, -3, 0, -3, 0, -3),
        ),
        LineType.ISO_LONG_DASH_TRIPLE_DOT.value: (
            "ISO long-dash triple-dot ____ ... ____ ... ____",
            lin_pattern(24, -3, 0, -3, 0, -3, 0, -3),
        ),
        LineType.ISO_DOT.value: (
            "ISO dot . . . . . . . . . . . . . . . . . . . . ",
            lin_pattern(0, -3),
        ),
        LineType.ISO_LONG_DASH_SHORT_DASH.value: (
            "ISO long-dash short-dash ____ __ ____ __ ____ _",
            lin_pattern(24, -3, 6, -3),
        ),
        LineType.ISO_LONG_DASH_DOUBLE_SHORT_DASH.value: (
            "ISO long-dash double-short-dash ____ __ __ ____",
            lin_pattern(24, -3, 6, -3, 6, -3),
        ),
        LineType.ISO_DASH_DOT.value: (
            "ISO dash dot __ . __ . __ . __ . __ . __ . __ . ",
            lin_pattern(12, -3, 0, -3),
        ),
        LineType.ISO_DOUBLE_DASH_DOT.value: (
            "ISO double-dash dot __ __ . __ __ . __ __ . __ _",
            lin_pattern(12, -3, 12, -3, 0, -3),
        ),
        LineType.ISO_DASH_DOUBLE_DOT.value: (
            "ISO dash double-dot __ . . __ . . __ . . __ . . ",
            lin_pattern(12, -3, 0, -3, 0, -3),
        ),
        LineType.ISO_DOUBLE_DASH_DOUBLE_DOT.value: (
            "ISO double-dash double-dot __ __ . . __ __ . . _",
            lin_pattern(12, -3, 12, -3, 0, -3, 0, -3),
        ),
        LineType.ISO_DASH_TRIPLE_DOT.value: (
            "ISO dash triple-dot __ . . . __ . . . __ . . . _",
            lin_pattern(12, -3, 0, -3, 0, -3, 0, -3),
        ),
        LineType.ISO_DOUBLE_DASH_TRIPLE_DOT.value: (
            "ISO double-dash triple-dot __ __ . . . __ __ . .",
            lin_pattern(12, -3, 12, -3, 0, -3, 0, -3, 0, -3),
        ),
    }

    # Scale factor to convert from linetype units (1/10 inch).
    LTYPE_SCALE = {
        Unit.INCH: 0.1,
        Unit.FOOT: 0.1 / 12,
        Unit.MILLIMETER: 2.54,
        Unit.CENTIMETER: 0.254,
        Unit.METER: 0.00254,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class ExportDXF(Export2D):

    UNITS_LOOKUP = {
        Unit.MICRO: 13,
        Unit.MILLIMETER: ezdxf.units.MM,
        Unit.CENTIMETER: ezdxf.units.CM,
        Unit.METER: ezdxf.units.M,
        Unit.INCH: ezdxf.units.IN,
        Unit.FOOT: ezdxf.units.FT,
    }

    METRIC_UNITS = {
        Unit.MILLIMETER,
        Unit.CENTIMETER,
        Unit.METER,
    }

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def __init__(
        self,
        version: str = ezdxf.DXF2013,
        unit: Unit = Unit.MILLIMETER,
        color: Optional[ColorIndex] = None,
        line_weight: Optional[float] = None,
        line_type: Optional[LineType] = None,
    ):
        if unit not in self.UNITS_LOOKUP:
            raise ValueError(f"unit `{unit.name}` not supported.")
        if unit in ExportDXF.METRIC_UNITS:
            self._linetype_scale = Export2D.LTYPE_SCALE[Unit.MILLIMETER]
        else:
            self._linetype_scale = 1
        self._document = ezdxf.new(
            dxfversion=version,
            units=self.UNITS_LOOKUP[unit],
            setup=False,
        )
        self._modelspace = self._document.modelspace()

        default_layer = self._document.layers.get("0")
        if color is not None:
            default_layer.color = color.value
        if line_weight is not None:
            default_layer.dxf.lineweight = round(line_weight * 100)
        if line_type is not None:
            default_layer.dxf.linetype = self._linetype(line_type)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def add_layer(
        self,
        name: str,
        *,
        color: Optional[ColorIndex] = None,
        line_weight: Optional[float] = None,
        line_type: Optional[LineType] = None,
    ) -> Self:
        """Create a layer definition

        Refer to :ref:`ezdxf layers <ezdxf-stable:layer_concept>` and
        :doc:`ezdxf layer tutorial <ezdxf-stable:tutorials/layers>`.

        :param name: layer definition name
        :param color: color index.
        :param linetype: ezdxf :doc:`line type <ezdxf-stable:concepts/linetypes>`
        """

        kwargs = {}

        if line_type is not None:
            linetype = self._linetype(line_type)
            kwargs["linetype"] = linetype

        if color is not None:
            kwargs["color"] = color.value

        if line_weight is not None:
            kwargs["lineweight"] = round(line_weight * 100)

        self._document.layers.add(name, **kwargs)
        return self

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _linetype(self, line_type: LineType) -> str:
        """Ensure that the specified LineType has been defined in the document,
        and return its string name."""
        linetype = line_type.value
        if linetype not in self._document.linetypes:
            # The linetype is not in the doc yet.
            # Add it from our available definitions.
            if linetype in Export2D.LINETYPE_DEFS:
                desc, pattern = Export2D.LINETYPE_DEFS.get(linetype)
                self._document.linetypes.add(
                    name=linetype,
                    pattern=[self._linetype_scale * v for v in pattern],
                    description=desc,
                )
            else:
                raise ValueError("Unknown linetype `{linetype}`.")
        return linetype

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def add_shape(self, shape: Shape, layer: str = "") -> Self:
        self._non_planar_point_count = 0
        attributes = {}
        if layer:
            attributes["layer"] = layer
        for edge in shape.edges():
            self._convert_edge(edge, attributes)
        if self._non_planar_point_count > 0:
            print(f"WARNING, exporting non-planar shape to 2D format.")
            print("  This is probably not what you want.")
            print(
                f"  {self._non_planar_point_count} points found outside the XY plane."
            )
        return self

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def write(self, file_name: str):

        # Reset the main CAD viewport of the model space to the
        # extents of its entities.
        # TODO: Expose viewport control to the user.
        # Do the same for ExportSVG.
        zoom.extents(self._modelspace)

        self._document.saveas(file_name)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_point(self, pt: Union[gp_XYZ, gp_Pnt, gp_Vec, Vector]) -> Vec2:
        """Create a Vec2 from a gp_Pnt or Vector.
        This method also checks for points z != 0."""
        if isinstance(pt, (gp_XYZ, gp_Pnt, gp_Vec)):
            (x, y, z) = (pt.X(), pt.Y(), pt.Z())
        elif isinstance(pt, Vector):
            (x, y, z) = pt.to_tuple()
        else:
            raise TypeError(
                f"Expected `gp_Pnt`, `gp_XYZ`, `gp_Vec`, or `Vector`.  Got `{type(pt).__name__}`."
            )
        if abs(z) > 1e-6:
            self._non_planar_point_count += 1
        return Vec2(x, y)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_line(self, edge: Edge, attribs: dict):
        self._modelspace.add_line(
            self._convert_point(edge.start_point()),
            self._convert_point(edge.end_point()),
            attribs,
        )

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_circle(self, edge: Edge, attribs: dict):
        geom = edge._geom_adaptor()
        circle = geom.Circle()
        center = self._convert_point(circle.Location())
        radius = circle.Radius()

        if edge.is_closed():
            self._modelspace.add_circle(center, radius, attribs)

        else:
            x_axis = circle.XAxis().Direction()
            z_axis = circle.Axis().Direction()
            phi = x_axis.AngleWithRef(gp_Dir(1, 0, 0), z_axis)
            u1 = geom.FirstParameter()
            u2 = geom.LastParameter()
            if z_axis.Z() > 0:
                angle1 = math.degrees(phi + u1)
                angle2 = math.degrees(phi + u2)
                ccw = True
            else:
                angle1 = math.degrees(phi - u1)
                angle2 = math.degrees(phi - u2)
                ccw = False
            self._modelspace.add_arc(center, radius, angle1, angle2, ccw, attribs)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_ellipse(self, edge: Edge, attribs: dict):
        geom = edge._geom_adaptor()
        ellipse = geom.Ellipse()
        minor_radius = ellipse.MinorRadius()
        major_radius = ellipse.MajorRadius()
        center = ellipse.Location()
        major_axis = major_radius * gp_Vec(ellipse.XAxis().Direction())
        main_dir = ellipse.Axis().Direction()
        if main_dir.Z() > 0:
            start = geom.FirstParameter()
            end = geom.LastParameter()
        else:
            start = -geom.LastParameter()
            end = -geom.FirstParameter()
        self._modelspace.add_ellipse(
            self._convert_point(center),
            self._convert_point(major_axis),
            minor_radius / major_radius,
            start,
            end,
            attribs,
        )

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_bspline(self, edge: Edge, attribs):

        # This reduces the B-Spline to degree 3, generally adding
        # poles and knots to approximate the original.
        # This also will convert basically any edge into a B-Spline.
        edge = edge.to_splines()

        # This pulls the underlying Geom_BSplineCurve out of the Edge.
        # The adaptor also supplies a parameter range for the curve.
        adaptor = edge._geom_adaptor()
        curve = adaptor.Curve().Curve()
        u1 = adaptor.FirstParameter()
        u2 = adaptor.LastParameter()

        # Extract the relevant segment of the curve.
        spline = GeomConvert.SplitBSplineCurve_s(
            curve,
            u1,
            u2,
            Export2D.PARAMETRIC_TOLERANCE,
        )

        # need to apply the transform on the geometry level
        t = edge.location.wrapped.Transformation()
        spline.Transform(t)

        order = spline.Degree() + 1
        knots = list(spline.KnotSequence())
        poles = [self._convert_point(p) for p in spline.Poles()]
        weights = (
            [spline.Weight(i) for i in range(1, spline.NbPoles() + 1)]
            if spline.IsRational()
            else None
        )

        if spline.IsPeriodic():
            pad = spline.NbKnots() - spline.LastUKnotIndex()
            poles += poles[:pad]

        dxf_spline = ezdxf.math.BSpline(poles, order, knots, weights)

        self._modelspace.add_spline(dxfattribs=attribs).apply_construction_tool(
            dxf_spline
        )

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_other(self, edge: Edge, attribs: dict):
        self._convert_bspline(edge, attribs)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    _CONVERTER_LOOKUP = {
        GeomType.LINE.name: _convert_line,
        GeomType.CIRCLE.name: _convert_circle,
        GeomType.ELLIPSE.name: _convert_ellipse,
        GeomType.BSPLINE.name: _convert_bspline,
    }

    def _convert_edge(self, edge: Edge, attribs: dict):
        geom_type = edge.geom_type()
        if False and geom_type not in self._CONVERTER_LOOKUP:
            article = "an" if geom_type[0] in "AEIOU" else "a"
            print(f"Hey neat, {article} {geom_type}!")
        convert = self._CONVERTER_LOOKUP.get(geom_type, ExportDXF._convert_other)
        convert(self, edge, attribs)


# ---------------------------------------------------------------------------
#
# ---------------------------------------------------------------------------


class ExportSVG(Export2D):
    """SVG file export functionality."""

    Converter = Callable[[Edge], ET.Element]

    # These are the units which are available in the Unit enum *and*
    # are valid units in SVG.
    _UNIT_STRING = {
        Unit.MILLIMETER: "mm",
        Unit.CENTIMETER: "cm",
        Unit.INCH: "in",
    }

    class Layer(object):
        def __init__(
            self,
            name: str,
            color: ColorIndex,
            line_weight: float,
            line_type: LineType,
        ):
            self.name = name
            self.color = color
            self.line_weight = line_weight
            self.line_type = line_type
            self.elements: List[ET.Element] = []

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def __init__(
        self,
        unit: Unit = Unit.MILLIMETER,
        scale: float = 1,
        margin: float = 0,
        fit_to_stroke: bool = True,
        precision: int = 6,
        color: ColorIndex = Export2D.DEFAULT_COLOR_INDEX,
        line_weight: float = Export2D.DEFAULT_LINE_WEIGHT,  # in millimeters
        line_type: LineType = Export2D.DEFAULT_LINE_TYPE,
    ):
        if unit not in ExportSVG._UNIT_STRING:
            raise ValueError(
                "Invalid unit.  Supported units are %s."
                % ", ".join(ExportSVG._UNIT_STRING.values())
            )
        self.unit = unit
        self.scale = scale
        self.margin = margin
        self.fit_to_stroke = fit_to_stroke
        self.precision = precision
        self._non_planar_point_count = 0
        self._layers: Dict[str, ExportSVG.Layer] = {}
        self._bounds: BoundBox = None

        # Add the default layer.
        self.add_layer("", color=color, line_weight=line_weight, line_type=line_type)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def add_layer(
        self,
        name: str,
        *,
        color: ColorIndex = Export2D.DEFAULT_COLOR_INDEX,
        line_weight: float = Export2D.DEFAULT_LINE_WEIGHT,  # in millimeters
        line_type: LineType = Export2D.DEFAULT_LINE_TYPE,
    ) -> Self:
        if name in self._layers:
            raise ValueError(f"Duplicate layer name '{name}'.")
        if line_type.value not in Export2D.LINETYPE_DEFS:
            raise ValueError(f"Unknow linetype `{line_type.value}`.")
        layer = ExportSVG.Layer(
            name=name,
            color=color,
            line_weight=line_weight,
            line_type=line_type,
        )
        self._layers[name] = layer
        return self

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def add_shape(self, shape: Shape, layer: str = ""):
        self._non_planar_point_count = 0
        if layer not in self._layers:
            raise ValueError(f"Undefined layer: {layer}.")
        layer = self._layers[layer]
        bb = shape.bounding_box()
        self._bounds = self._bounds.add(bb) if self._bounds else bb
        elements = [self._convert_edge(edge) for edge in shape.edges()]
        layer.elements.extend(elements)
        if self._non_planar_point_count > 0:
            print(f"WARNING, exporting non-planar shape to 2D format.")
            print("  This is probably not what you want.")
            print(
                f"  {self._non_planar_point_count} points found outside the XY plane."
            )

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def path_point(self, pt: Union[gp_Pnt, Vector]) -> complex:
        """Create a complex point from a gp_Pnt or Vector.
        We are using complex because that is what svgpathtools wants.
        This method also checks for points z != 0."""
        if isinstance(pt, gp_Pnt):
            xyz = pt.X(), pt.Y(), pt.Z()
        elif isinstance(pt, Vector):
            xyz = pt.X, pt.Y, pt.Z
        else:
            raise TypeError(
                f"Expected `gp_Pnt` or `Vector`.  Got `{type(pt).__name__}`."
            )
        x, y, z = tuple(round(v, self.precision) for v in xyz)
        if z != 0:
            self._non_planar_point_count += 1
        return complex(x, y)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_line(self, edge: Edge) -> ET.Element:
        p0 = self.path_point(edge @ 0)
        p1 = self.path_point(edge @ 1)
        result = ET.Element(
            "line",
            {
                "x1": str(p0.real),
                "y1": str(p0.imag),
                "x2": str(p1.real),
                "y2": str(p1.imag),
            },
        )
        return result

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_circle(self, edge: Edge) -> ET.Element:
        geom = edge._geom_adaptor()
        circle = geom.Circle()
        radius = circle.Radius()
        center = circle.Location()

        if edge.is_closed():
            c = self.path_point(center)
            result = ET.Element(
                "circle", {"cx": str(c.real), "cy": str(c.imag), "r": str(radius)}
            )
        else:
            x_axis = circle.XAxis().Direction()
            z_axis = circle.Axis().Direction()
            phi = x_axis.AngleWithRef(gp_Dir(1, 0, 0), z_axis)
            if z_axis.Z() > 0:
                u1 = geom.FirstParameter()
                u2 = geom.LastParameter()
                sweep = True
            else:
                u1 = -geom.LastParameter()
                u2 = -geom.FirstParameter()
                sweep = False
            du = u2 - u1
            large_arc = (du < -math.pi) or (du > math.pi)

            start = self.path_point(edge @ 0)
            end = self.path_point(edge @ 1)
            radius = complex(radius, radius)
            rotation = math.degrees(phi)
            arc = PT.Arc(start, radius, rotation, large_arc, sweep, end)
            path = PT.Path(arc)
            result = ET.Element("path", {"d": path.d()})
        return result

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_ellipse(self, edge: Edge) -> ET.Element:
        geom = edge._geom_adaptor()
        ellipse = geom.Ellipse()
        minor_radius = ellipse.MinorRadius()
        major_radius = ellipse.MajorRadius()
        x_axis = ellipse.XAxis().Direction()
        z_axis = ellipse.Axis().Direction()
        if z_axis.Z() > 0:
            u1 = geom.FirstParameter()
            u2 = geom.LastParameter()
            sweep = True
        else:
            u1 = -geom.LastParameter()
            u2 = -geom.FirstParameter()
            sweep = False
        du = u2 - u1
        large_arc = (du < -math.pi) or (du > math.pi)

        start = self.path_point(edge @ 0)
        end = self.path_point(edge @ 1)
        radius = complex(major_radius, minor_radius)
        rotation = math.degrees(x_axis.AngleWithRef(gp_Dir(1, 0, 0), z_axis))
        if edge.is_closed():
            midway = self.path_point(edge @ 0.5)
            arcs = [
                PT.Arc(start, radius, rotation, False, sweep, midway),
                PT.Arc(midway, radius, rotation, False, sweep, end),
            ]
        else:
            arcs = [PT.Arc(start, radius, rotation, large_arc, sweep, end)]
        path = PT.Path(*arcs)
        result = ET.Element("path", {"d": path.d()})
        return result

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_bspline(self, edge: Edge) -> ET.Element:

        # This reduces the B-Spline to degree 3, generally adding
        # poles and knots to approximate the original.
        # This also will convert basically any edge into a B-Spline.
        edge = edge.to_splines()

        # This pulls the underlying Geom_BSplineCurve out of the Edge.
        # The adaptor also supplies a parameter range for the curve.
        adaptor = edge._geom_adaptor()
        spline = adaptor.Curve().Curve()
        u1 = adaptor.FirstParameter()
        u2 = adaptor.LastParameter()

        # Apply the shape location to the geometry.
        t = edge.location.wrapped.Transformation()
        spline.Transform(t)
        # describe_bspline(spline)

        # Convert the B-Spline to Bezier curves.
        # From the OCCT 7.6.0 documentation:
        # > Note: ParametricTolerance is not used.
        converter = GeomConvert_BSplineCurveToBezierCurve(
            spline, u1, u2, Export2D.PARAMETRIC_TOLERANCE
        )

        def make_segment(
            bezier: Geom_BezierCurve,
        ) -> Union[PT.Line, PT.QuadraticBezier, PT.CubicBezier]:
            p = [self.path_point(p) for p in bezier.Poles()]
            if len(p) == 2:
                result = PT.Line(start=p[0], end=p[1])
            elif len(p) == 3:
                result = PT.QuadraticBezier(start=p[0], control=p[1], end=p[2])
            elif len(p) == 4:
                result = PT.CubicBezier(
                    start=p[0], control1=p[1], control2=p[2], end=p[3]
                )
            else:
                raise ValueError(f"Surprising Bézier of degree {bezier.Degree()}!")
            return result

        segments = [
            make_segment(converter.Arc(i)) for i in range(1, converter.NbArcs() + 1)
        ]
        path = PT.Path(*segments)
        result = ET.Element("path", {"d": path.d()})
        return result

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _convert_other(self, edge: Edge) -> ET.Element:
        # _convert_bspline can actually handle basically anything
        # because it calls Edge.to_splines() first thing.
        return self._convert_bspline(edge)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    _CONVERTER_LOOKUP = {
        GeomType.LINE.name: _convert_line,
        GeomType.CIRCLE.name: _convert_circle,
        GeomType.ELLIPSE.name: _convert_ellipse,
        GeomType.BSPLINE.name: _convert_bspline,
    }

    def _convert_edge(self, edge: Edge) -> ET.Element:
        geom_type = edge.geom_type()
        if False and geom_type not in self._CONVERTER_LOOKUP:
            article = "an" if geom_type[0] in "AEIOU" else "a"
            print(f"Hey neat, {article} {geom_type}!")
        convert = self._CONVERTER_LOOKUP.get(geom_type, ExportSVG._convert_other)
        result = convert(self, edge)
        return result

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def _group_for_layer(self, layer: Layer, attribs: Dict = {}) -> ET.Element:
        (r, g, b) = (
            (0, 0, 0) if layer.color == ColorIndex.BLACK else aci2rgb(layer.color.value)
        )
        lwscale = unit_conversion_scale(Unit.MILLIMETER, self.unit)
        stroke_width = layer.line_weight * lwscale
        result = ET.Element(
            "g",
            attribs
            | {
                "stroke": f"rgb({r},{g},{b})",
                "stroke-width": f"{stroke_width}",
                "fill": "none",
            },
        )
        if layer.name:
            result.set("id", layer.name)

        if layer.line_type is not LineType.CONTINUOUS:
            ltname = layer.line_type.value
            _, pattern = Export2D.LINETYPE_DEFS[ltname]
            ltscale = ExportSVG.LTYPE_SCALE[self.unit] * layer.line_weight
            dash_array = [
                f"{round(ltscale * abs(e), self.precision)}" for e in pattern[1:]
            ]
            result.set("stroke-dasharray", " ".join(dash_array))

        for element in layer.elements:
            result.append(element)

        return result

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

    def write(self, path: str):

        bb = self._bounds
        margin = self.margin
        if self.fit_to_stroke:
            max_line_weight = max(l.line_weight for l in self._layers.values())
            margin += max_line_weight / 2
        view_left = round(+bb.min.X - margin, self.precision)
        view_top = round(-bb.max.Y - margin, self.precision)
        view_width = round(bb.size.X + 2 * margin, self.precision)
        view_height = round(bb.size.Y + 2 * margin, self.precision)
        view_box = [str(f) for f in [view_left, view_top, view_width, view_height]]
        doc_width = round(view_width * self.scale, self.precision)
        doc_height = round(view_height * self.scale, self.precision)
        doc_unit = self._UNIT_STRING.get(self.unit, "")
        svg = ET.Element(
            "svg",
            {
                "width": f"{doc_width}{doc_unit}",
                "height": f"{doc_height}{doc_unit}",
                "viewBox": " ".join(view_box),
                "version": "1.1",
                "xmlns": "http://www.w3.org/2000/svg",
            },
        )

        container_group = ET.Element(
            "g",
            {
                "transform": f"scale(1,-1)",
                "stroke-linecap": "round",
            },
        )
        svg.append(container_group)

        for _, layer in self._layers.items():
            layer_group = self._group_for_layer(layer)
            container_group.append(layer_group)

        xml = ET.ElementTree(svg)
        ET.indent(xml, "  ")
        xml.write(path, encoding="utf-8", xml_declaration=True, default_namespace=False)
