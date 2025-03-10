import numpy as np
import pytest
from dolfinx import fem

import festim as F

test_mesh_1d = F.Mesh1D(vertices=np.linspace(0, 1, 100))
test_functionspace = fem.functionspace(test_mesh_1d.mesh, ("CG", 1))


@pytest.mark.parametrize(
    "value", ["coucou", 1.0, 1, fem.Constant(test_mesh_1d.mesh, 1.0)]
)
def test_Typeerror_raised_when_wrong_object_given_to_Advection(value):
    "test"

    my_species = F.Species("H")
    my_subdomain = F.VolumeSubdomain(id=1, material="dummy_mat")

    with pytest.raises(
        TypeError,
        match=f"velocity must be a fem.Function, or callable not {type(value)}",
    ):
        F.AdvectionTerm(velocity=value, subdomain=my_subdomain, species=my_species)


@pytest.mark.parametrize(
    "value",
    ["coucou", 1.0, 1, F.SurfaceSubdomain(id=1)],
)
def test_subdomain_setter(value):
    "test"

    my_species = F.Species("H")

    with pytest.raises(
        TypeError,
        match=f"Subdomain must be a festim.Subdomain object, not {type(value)}",
    ):
        F.AdvectionTerm(velocity=None, subdomain=value, species=my_species)


@pytest.mark.parametrize(
    "value",
    ["coucou", 1.0, 1, F.SurfaceSubdomain(id=1)],
)
def test_species_setter_type_error(value):
    "test"

    my_subdomain = F.VolumeSubdomain(id=1, material="dummy_mat")

    with pytest.raises(
        TypeError,
        match=f"elements of species must be of type festim.Species not {type(value)}",
    ):
        F.AdvectionTerm(velocity=None, subdomain=my_subdomain, species=value)


@pytest.mark.parametrize(
    "value",
    [F.Species("H"), [F.Species("D"), F.Species("test")]],
)
def test_species_setter_changes_input_to_list(value):
    "test"

    my_subdomain = F.VolumeSubdomain(id=1, material="dummy_mat")

    my_advection_term = F.AdvectionTerm(
        velocity=None, subdomain=my_subdomain, species=value
    )

    assert isinstance(my_advection_term.species, list)
