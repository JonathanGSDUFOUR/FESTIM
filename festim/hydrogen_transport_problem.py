from dolfinx import fem
from dolfinx.nls.petsc import NewtonSolver
import ufl
from mpi4py import MPI
from dolfinx.fem import Function
from dolfinx.mesh import meshtags
from ufl import TestFunction, dot, grad, Measure
import numpy as np

import festim as F


class HydrogenTransportProblem:
    """
    Hydrogen Transport Problem.

    Args:
        mesh (festim.Mesh): the mesh of the model
        subdomains (list of festim.Subdomain): the subdomains of the model
        species (list of festim.Species): the species of the model
        temperature (float or fem.Constant): the temperature of the model
        sources (list of festim.Source): the hydrogen sources of the model
        boundary_conditions (list of festim.BoundaryCondition): the boundary
            conditions of the model
        solver_parameters (dict): the solver parameters of the model
        exports (list of festim.Export): the exports of the model

    Attributes:
        mesh (festim.Mesh): the mesh of the model
        subdomains (list of festim.Subdomain): the subdomains of the model
        species (list of festim.Species): the species of the model
        temperature (fem.Constant): the temperature of the model
        boundary_conditions (list of festim.BoundaryCondition): the boundary
            conditions of the model
        solver_parameters (dict): the solver parameters of the model
        exports (list of festim.Export): the exports of the model
        dx (dolfinx.fem.dx): the volume measure of the model
        ds (dolfinx.fem.ds): the surface measure of the model
        function_space (dolfinx.fem.FunctionSpace): the function space of the
            model
        facet_meshtags (dolfinx.cpp.mesh.MeshTags): the facet tags of the model
        volume_meshtags (dolfinx.cpp.mesh.MeshTags): the volume tags of the
            model
        formulation (ufl.form.Form): the formulation of the model
        solver (dolfinx.nls.newton.NewtonSolver): the solver of the model

    Usage:
        >>> import festim as F
        >>> my_model = F.HydrogenTransportProblem()
        >>> my_model.mesh = F.Mesh(...)
        >>> my_model.subdomains = [F.Subdomain(...)]
        >>> my_model.species = [F.Species(name="H"), F.Species(name="Trap")]
        >>> my_model.temperature = 500
        >>> my_model.sources = [F.Source(...)]
        >>> my_model.boundary_conditions = [F.BoundaryCondition(...)]
        >>> my_model.initialise()

        or

        >>> my_model = F.HydrogenTransportProblem(
        ...     mesh=F.Mesh(...),
        ...     subdomains=[F.Subdomain(...)],
        ...     species=[F.Species(name="H"), F.Species(name="Trap")],
        ... )
        >>> my_model.initialise()

    """

    def __init__(
        self,
        mesh=None,
        subdomains=[],
        species=[],
        temperature=None,
        sources=[],
        boundary_conditions=[],
        solver_parameters=None,
        exports=[],
    ) -> None:
        self.mesh = mesh
        self.subdomains = subdomains
        self.species = species
        self.temperature = temperature
        self.sources = sources
        self.boundary_conditions = boundary_conditions
        self.solver_parameters = solver_parameters
        self.exports = exports

        self.dx = None
        self.ds = None
        self.function_space = None
        self.facet_meshtags = None
        self.volume_meshtags = None
        self.formulation = None
        self.volume_subdomains = []

    @property
    def temperature(self):
        return self._temperature

    @temperature.setter
    def temperature(self, value):
        if value is None:
            self._temperature = value
        else:
            self._temperature = F.as_fenics_constant(value, self.mesh.mesh)

    def initialise(self):
        self.define_function_space()
        self.define_markers_and_measures()
        self.assign_functions_to_species()
        self.create_formulation()

    def define_function_space(self):
        elements = ufl.FiniteElement("CG", self.mesh.mesh.ufl_cell(), 1)
        self.function_space = fem.FunctionSpace(self.mesh.mesh, elements)

    def define_markers_and_measures(self):
        """Defines the markers and measures of the model"""

        dofs_facets, tags_facets = [], []

        # TODO this should be a property of mesh
        fdim = self.mesh.mesh.topology.dim - 1
        vdim = self.mesh.mesh.topology.dim

        # find all cells in domain and mark them as 0
        num_cells = self.mesh.mesh.topology.index_map(vdim).size_local
        mesh_cell_indices = np.arange(num_cells, dtype=np.int32)
        tags_volumes = np.full(num_cells, 0, dtype=np.int32)

        for sub_dom in self.subdomains:
            if isinstance(sub_dom, F.SurfaceSubdomain1D):
                dof = sub_dom.locate_dof(self.function_space)
                dofs_facets.append(dof)
                tags_facets.append(sub_dom.id)
            if isinstance(sub_dom, F.VolumeSubdomain1D):
                # find all cells in subdomain and mark them as sub_dom.id
                self.volume_subdomains.append(sub_dom)
                entities = sub_dom.locate_subdomain_entities(self.mesh.mesh, vdim)
                tags_volumes[entities] = sub_dom.id

        # dofs and tags need to be in np.in32 format for meshtags
        dofs_facets = np.array(dofs_facets, dtype=np.int32)
        tags_facets = np.array(tags_facets, dtype=np.int32)

        # define mesh tags
        self.facet_meshtags = meshtags(self.mesh.mesh, fdim, dofs_facets, tags_facets)
        self.volume_meshtags = meshtags(
            self.mesh.mesh, vdim, mesh_cell_indices, tags_volumes
        )

        # define measures
        self.ds = Measure(
            "ds", domain=self.mesh.mesh, subdomain_data=self.facet_meshtags
        )
        self.dx = Measure(
            "dx", domain=self.mesh.mesh, subdomain_data=self.volume_meshtags
        )

    def assign_functions_to_species(self):
        """Creates for each species the solution, prev solution and test function"""
        if len(self.species) > 1:
            raise NotImplementedError("Multiple species not implemented yet")
        for spe in self.species:
            spe.solution = Function(self.function_space)
            spe.prev_solution = Function(self.function_space)
            spe.test_function = TestFunction(self.function_space)

    def create_formulation(self):
        """Creates the formulation of the model"""
        if len(self.sources) > 1:
            raise NotImplementedError("Sources not implemented yet")
        if len(self.species) > 1:
            raise NotImplementedError("Multiple species not implemented yet")

        # TODO expose dt as parameter of the model
        dt = fem.Constant(self.mesh.mesh, 1 / 20)

        self.dt = dt  # TODO remove this

        self.formulation = 0

        for spe in self.species:
            u = spe.solution
            u_n = spe.prev_solution
            v = spe.test_function

            for vol in self.volume_subdomains:
                D = vol.material.get_diffusion_coefficient(
                    self.mesh.mesh, self.temperature
                )

                self.formulation += dot(D * grad(u), grad(v)) * self.dx(vol.id)
                self.formulation += ((u - u_n) / dt) * v * self.dx(vol.id)

                # add sources
                # TODO implement this
                # for source in self.sources:
                #     # f = Constant(my_mesh.mesh, (PETSc.ScalarType(0)))
                #     if source.species == spe:
                #         formulation += source * v * self.dx
                # add fluxes
                # TODO implement this
                # for bc in self.boundary_conditions:
                #     pass
                #     if bc.species == spe and bc.type != "dirichlet":
                #         formulation += bc * v * self.ds

    def create_solver(self):
        """Creates the solver of the model"""
        problem = fem.petsc.NonlinearProblem(
            self.formulation, self.species[0].solution, bcs=self.boundary_conditions
        )
        solver = NewtonSolver(MPI.COMM_WORLD, problem)
        self.solver = solver