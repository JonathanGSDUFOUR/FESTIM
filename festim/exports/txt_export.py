import fenics as f
import numpy as np
import festim
import warnings
import os

warnings.simplefilter("always", DeprecationWarning)


class TXTExport(festim.Export):
    """
    Args:
        field (str): the exported field ("solute", "1", "retention",
            "T"...)
        filename (str): the filename (must end with .txt).
        write_at_last (bool): if True, the data will be exported at
            the last export time. Otherwise, the data will be exported
            at each export time. Defaults to False.
        times (list, optional): if provided, the field will be
            exported at these timesteps. Otherwise exports at all
            timesteps. Defaults to None.
        header_format (str, optional): the format of column headers.
            Defautls to ".2e".

    Attributes:
        data (np.array): the data array of the exported field. The first column
            is the mesh vertices. Each next column is the field profile at the specific
            export time.
        header (str): the header of the exported file.
    """

    def __init__(
        self, field, filename, times=None, write_at_last=False, header_format=".2e"
    ) -> None:
        super().__init__(field=field)
        if times:
            self.times = sorted(times)
        else:
            self.times = times
        self.filename = filename
        self.write_at_last = write_at_last
        self.header_format = header_format

        self.data = None
        self.header = None
        self._unique_indices = None
        self._V = None

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        if value is not None:
            if not isinstance(value, str):
                raise TypeError("filename must be a string")
            if not value.endswith(".txt"):
                raise ValueError("filename must end with .txt")
        self._filename = value

    def is_it_time_to_export(self, current_time):
        if self.times is None:
            return True
        for time in self.times:
            if np.isclose(time, current_time, atol=0):
                return True
        return False

    def is_last(self, current_time, final_time):
        if final_time is None:
            # write if steady
            return True
        elif self.times is None:
            if np.isclose(current_time, final_time, atol=0):
                # write at final time if exports at each timestep
                return True
        else:
            if np.isclose(current_time, self.times[-1], atol=0):
                # write at final time if exports at specific times
                return True
        return False

    def initialise_TXTExport(self, mesh, project_to_DG=False, materials=None):

        if project_to_DG:
            self._V = f.FunctionSpace(mesh, "DG", 1)
        else:
            self._V = f.FunctionSpace(mesh, "CG", 1)

        x = f.interpolate(f.Expression("x[0]", degree=1), self._V)
        x_column = np.transpose([x.vector()[:]])

        # if chemical_pot is True or trap_element_type is DG, get indices of duplicates near interfaces
        # and indices of the first elements from a pair of duplicates otherwise
        if project_to_DG:
            # Collect all borders
            borders = []
            for material in materials:
                if material.borders:
                    for border in material.borders:
                        borders.append(border)
            borders = np.unique(borders)

            # Find indices of the closest duplicates to interfaces
            border_indices = []
            for border in borders:
                closest_indx = np.abs(x_column - border).argmin()
                closest_x = x_column[closest_indx]
                for ind in np.where(x_column == closest_x)[0]:
                    border_indices.append(ind)

            # Find indices of first elements in duplicated pairs and mesh borders
            _, mesh_indices = np.unique(x_column, return_index=True)

            # Get unique indices from both arrays preserving the order in unsorted x-array
            unique_indices = []
            for indx in np.argsort(x_column, axis=0)[:, 0]:
                if (indx in mesh_indices) or (indx in border_indices):
                    unique_indices.append(indx)

            self._unique_indices = np.array(unique_indices)

        else:
            # Get list of unique indices as integers
            self._unique_indices = np.argsort(x_column, axis=0)[:, 0]

        self.data = x_column[self._unique_indices]
        self.header = "x"

    def write(self, current_time, final_time):

        if self.is_it_time_to_export(current_time):
            solution = f.project(self.function, self._V)
            solution_column = np.transpose(solution.vector()[:])

            # if the directory doesn't exist
            # create it
            dirname = os.path.dirname(self.filename)
            if not os.path.exists(dirname):
                os.makedirs(dirname, exist_ok=True)

            # if steady, add the corresponding label
            # else append new export time to the header
            steady = final_time is None
            if steady:
                self.header += ",t=steady"
            else:
                self.header += f",t={format(current_time, self.header_format)}s"

            # Add new column of filtered and sorted data
            self.data = np.column_stack(
                [self.data, solution_column[self._unique_indices]]
            )

            if (
                self.write_at_last and self.is_last(current_time, final_time)
            ) or not self.write_at_last:

                # Write data
                np.savetxt(
                    self.filename,
                    self.data,
                    header=self.header,
                    delimiter=",",
                    comments="",
                )
