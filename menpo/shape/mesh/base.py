import numpy as np
from warnings import warn

Delaunay = None  # expensive, from scipy.spatial

from .. import PointCloud
from ..adjacency import mask_adjacency_array, reindex_adjacency_array
from menpo.visualize import TriMeshViewer

from .normals import compute_normals


def trilist_to_adjacency_array(trilist):
    wrap_around_adj = np.hstack([trilist[:, -1][..., None],
                                 trilist[:, 0][..., None]])
    # Build the array of all pairs
    return np.concatenate([trilist[:, :2],
                           trilist[:, 1:],
                           wrap_around_adj])


class TriMesh(PointCloud):
    r"""
    A pointcloud with a connectivity defined by a triangle list. These are
    designed to be explicitly 2D or 3D.

    Parameters
    ----------
    points : ``(n_points, n_dims)`` `ndarray`
        The array representing the points.
    trilist : ``(M, 3)`` `ndarray` or `None`, optional
        The triangle list. If `None`, a Delaunay triangulation of
        the points will be used instead.
    copy: `bool`, optional
        If ``False``, the points will not be copied on assignment.
        Any trilist will also not be copied.
        In general this should only be used if you know what you are doing.
    """
    def __init__(self, points, trilist=None, copy=True):
        #TODO add inheritance from Graph once implemented
        super(TriMesh, self).__init__(points, copy=copy)
        if trilist is None:
            global Delaunay
            if Delaunay is None:
                from scipy.spatial import Delaunay  # expensive
            trilist = Delaunay(points).simplices
        if not copy:
            if not trilist.flags.c_contiguous:
                warn('The copy flag was NOT honoured. A copy HAS been made. '
                     'Please ensure the data you pass is C-contiguous.')
                trilist = np.array(trilist, copy=True, order='C')
        else:
            trilist = np.array(trilist, copy=True, order='C')
        self.trilist = trilist

    def __str__(self):
        return '{}, n_tris: {}'.format(PointCloud.__str__(self),
                                       self.n_tris)

    @property
    def n_tris(self):
        r"""
        The number of triangles in the triangle list.

        :type: `int`
        """
        return len(self.trilist)

    def tojson(self):
        r"""
        Convert this `TriMesh` to a dictionary JSON representation.

        Returns
        -------
        dictionary with 'points' and 'trilist' keys. Both are lists suitable
        for use in the by the `json` standard library package.
        """
        json_dict = PointCloud.tojson(self)
        json_dict['trilist'] = self.trilist.tolist()
        return json_dict

    def from_mask(self, mask):
        """
        A 1D boolean array with the same number of elements as the number of
        points in the TriMesh. This is then broadcast across the dimensions
        of the mesh and returns a new mesh containing only those
        points that were ``True`` in the mask.

        Parameters
        ----------
        mask : ``(n_points,)`` `ndarray`
            1D array of booleans

        Returns
        -------
        mesh : :map:`TriMesh`
            A new mesh that has been masked.
        """
        if mask.shape[0] != self.n_points:
            raise ValueError('Mask must be a 1D boolean array of the same '
                             'number of entries as points in this TriMesh.')

        tm = self.copy()
        if np.all(mask):  # Fast path for all true
            return tm
        else:
            # Recalculate the mask to remove isolated vertices
            isolated_mask = self._isolated_mask(mask)
            # Recreate the adjacency array with the updated mask
            masked_adj = mask_adjacency_array(isolated_mask, self.trilist)
            tm.trilist = reindex_adjacency_array(masked_adj)
            tm.points = tm.points[isolated_mask, :]
            return tm

    def _isolated_mask(self, mask):
        # Find the triangles we need to keep
        masked_adj = mask_adjacency_array(mask, self.trilist)
        # Find isolated vertices (vertices that don't exist in valid
        # triangles)
        isolated_indices = np.setdiff1d(np.nonzero(mask)[0], masked_adj)

        # Create a 'new mask' that contains the points the use asked
        # for MINUS the points that we can't create triangles for
        new_mask = mask.copy()
        new_mask[isolated_indices] = False
        return new_mask

    def as_pointgraph(self, copy=True):
        """
        Converts the TriMesh to a :map:`PointUndirectedGraph`.

        Parameters
        ----------
        copy : `bool`
            If ``True``, the graph will be a copy.

        Returns
        -------
        pointgraph : :map:`PointUndirectedGraph`
            The point graph.
        """
        from .. import PointUndirectedGraph
        # Since we have triangles we need the last connection
        # that 'completes' the triangle
        adjacency_array = trilist_to_adjacency_array(self.trilist)
        pg = PointUndirectedGraph(self.points, adjacency_array, copy=copy)
        # This is always a copy
        pg.landmarks = self.landmarks
        return pg

    def vertex_normals(self):
        r"""
        Compute the per-vertex normals from the current set of points and
        triangle list. Only valid for 3D dimensional meshes.

        Returns
        -------
        normals : ``(n_points, 3)`` `ndarray`
            Normal at each point.

        Raises
        ------
        ValueError
            If mesh is not 3D
        """
        if self.n_dims != 3:
            raise ValueError("Normals are only valid for 3D meshes")
        return compute_normals(self.points, self.trilist)[0]

    def face_normals(self):
        r"""
        Compute the face normals from the current set of points and
        triangle list. Only valid for 3D dimensional meshes.

        Returns
        -------
        normals : ``(n_tris, 3)`` `ndarray`
            Normal at each face.

        Raises
        ------
        ValueError
            If mesh is not 3D
        """
        if self.n_dims != 3:
            raise ValueError("Normals are only valid for 3D meshes")
        return compute_normals(self.points, self.trilist)[1]

    def view(self, figure_id=None, new_figure=False, image_view=True,
             render_lines=True, line_colour='r', line_style='-', line_width=1.,
             render_markers=True, marker_style='o', marker_size=20,
             marker_face_colour='k', marker_edge_colour='k',
             marker_edge_width=1., render_axes=True,
             axes_font_name='sans-serif', axes_font_size=10,
             axes_font_style='normal', axes_font_weight='normal',
             axes_x_limits=None, axes_y_limits=None, figure_size=None,
             label=None):
        r"""
        Visualization of the TriMesh.

        Parameters
        ----------
        figure_id : `object`, optional
            The id of the figure to be used.
        new_figure : `bool`, optional
            If ``True``, a new figure is created.
        image_view : `bool`, optional
            If ``True``, the x and y axes are flipped.
        render_lines : `bool`, optional
            If ``True``, the edges will be rendered.
        line_colour : {``r``, ``g``, ``b``, ``c``, ``m``, ``k``, ``w``} or
                      ``(3, )`` `ndarray`, optional
            The colour of the lines.
        line_style : {``-``, ``--``, ``-.``, ``:``}, optional
            The style of the lines.
        line_width : `float`, optional
            The width of the lines.
        render_markers : `bool`, optional
            If ``True``, the markers will be rendered.
        marker_style : {``.``, ``,``, ``o``, ``v``, ``^``, ``<``, ``>``, ``+``,
                        ``x``, ``D``, ``d``, ``s``, ``p``, ``*``, ``h``, ``H``,
                        ``1``, ``2``, ``3``, ``4``, ``8``}, optional
            The style of the markers.
        marker_size : `int`, optional
            The size of the markers in points^2.
        marker_face_colour : {``r``, ``g``, ``b``, ``c``, ``m``, ``k``, ``w``}
                             or ``(3, )`` `ndarray`, optional
            The face (filling) colour of the markers.
        marker_edge_colour : {``r``, ``g``, ``b``, ``c``, ``m``, ``k``, ``w``}
                             or ``(3, )`` `ndarray`, optional
            The edge colour of the markers.
        marker_edge_width : `float`, optional
            The width of the markers' edge.
        render_axes : `bool`, optional
            If ``True``, the axes will be rendered.
        axes_font_name : {``serif``, ``sans-serif``, ``cursive``, ``fantasy``,
                          ``monospace``}, optional
            The font of the axes.
        axes_font_size : `int`, optional
            The font size of the axes.
        axes_font_style : {``normal``, ``italic``, ``oblique``}, optional
            The font style of the axes.
        axes_font_weight : {``ultralight``, ``light``, ``normal``, ``regular``,
                            ``book``, ``medium``, ``roman``, ``semibold``,
                            ``demibold``, ``demi``, ``bold``, ``heavy``,
                            ``extra bold``, ``black``}, optional
            The font weight of the axes.
        axes_x_limits : (`float`, `float`) or `None`, optional
            The limits of the x axis.
        axes_y_limits : (`float`, `float`) or `None`, optional
            The limits of the y axis.
        figure_size : (`float`, `float`) or `None`, optional
            The size of the figure in inches.
        label : `str`, optional
            The name entry in case of a legend.

        Returns
        -------
        viewer : :map:`TriMeshViewer`
            The viewer object.

        Raises
        ------
        ValueError
            If `not self.n_dims in [2, 3]`.
        """
        return TriMeshViewer(figure_id, new_figure, self.points,
                             self.trilist).render(
            image_view=image_view, render_lines=render_lines,
            line_colour=line_colour, line_style=line_style,
            line_width=line_width, render_markers=render_markers,
            marker_style=marker_style, marker_size=marker_size,
            marker_face_colour=marker_face_colour,
            marker_edge_colour=marker_edge_colour,
            marker_edge_width=marker_edge_width, render_axes=render_axes,
            axes_font_name=axes_font_name, axes_font_size=axes_font_size,
            axes_font_style=axes_font_style, axes_font_weight=axes_font_weight,
            axes_x_limits=axes_x_limits, axes_y_limits=axes_y_limits,
            figure_size=figure_size, label=label)

    def view_widget(self, popup=False):
        r"""
        Visualization of the TriMesh using the :map:`visualize_pointclouds`
        widget.

        Parameters
        ----------
        popup : `bool`, optional
            If ``True``, the widget will be rendered in a popup window.
        """
        from menpo.visualize import visualize_pointclouds
        visualize_pointclouds(self, popup=popup, figure_size=(6, 4))
