import festim as F
from dolfinx import fem, mesh
import mpi4py.MPI as MPI
import os
import numpy as np
import pytest


def test_init():
    """Tests the initialisation of XDMFExport"""
    species = F.Species("H")
    my_export = F.XDMFExport(filename="my_export.xdmf", field=species)

    assert my_export.filename == "my_export.xdmf"
    assert my_export.field == [species]


def test_write(tmp_path):
    """Tests the write method of XDMFExport creates a file"""
    species = F.Species("H")
    filename = os.path.join(tmp_path, "test.xdmf")
    my_export = F.XDMFExport(filename=filename, field=species)

    my_export.define_writer(MPI.COMM_WORLD)

    domain = mesh.create_unit_cube(MPI.COMM_WORLD, 10, 10, 10)
    V = fem.FunctionSpace(domain, ("Lagrange", 1))
    u = fem.Function(V)

    species.post_processing_solution = u

    for t in [0, 1, 2, 3]:
        my_export.write(t=t)

    assert os.path.exists(filename)


def test_integration_with_HTransportProblem(tmp_path):
    """Tests that XDMFExport can be used in conjunction with HTransportProblem"""
    my_model = F.HydrogenTransportProblem()
    my_model.mesh = F.Mesh1D(vertices=np.linspace(0, 1))
    my_mat = F.Material(D_0=1.9e-7, E_D=0.2, name="my_mat")
    my_subdomain = F.VolumeSubdomain1D(id=1, borders=[0, 1], material=my_mat)
    my_model.subdomains = [my_subdomain]
    my_model.temperature = 500.0
    my_model.species = [F.Species("H")]
    filename = os.path.join(tmp_path, "test.xdmf")
    my_model.exports = [F.XDMFExport(filename=filename, field=my_model.species)]

    my_model.settings = F.Settings(atol=1, rtol=0.1, final_time=1)
    my_model.settings.stepsize = F.Stepsize(initial_value=0.5)
    my_model.initialise()
    my_model.run()

    # checks that filename exists
    assert os.path.exists(filename)


def test_field_attribute_is_always_list():
    """Test that the field attribute is always a list"""
    my_export = F.XDMFExport("my_export.xdmf", field=F.Species("H"))
    assert isinstance(my_export.field, list)

    my_export = F.XDMFExport("my_export.xdmf", field=[F.Species("H")])
    assert isinstance(my_export.field, list)


@pytest.mark.parametrize("field", [["H", 2], 1, [F.Species("H"), 1]])
def test_field_attribute_raises_error_when_invalid_type(field):
    """Test that the field attribute raises an error if the type is not festim.Species or list"""
    with pytest.raises(TypeError):
        F.XDMFExport("my_export.xdmf", field=field)


def test_filename_raises_error_with_wrong_extension():
    """Test that the filename attribute raises an error if the extension is not .xdmf"""
    with pytest.raises(ValueError):
        F.XDMFExport("my_export.txt", field=[F.Species("H")])


def test_filename_raises_error_when_wrong_type():
    """Test that the filename attribute raises an error if the file is not str"""
    with pytest.raises(TypeError):
        F.XDMFExport(1, field=[F.Species("H")])


def test_xdmf_field_as_string_found_in_species(tmpdir):
    my_model = F.HydrogenTransportProblem()
    my_model.mesh = F.Mesh1D(vertices=np.array([0.0, 1.0, 2.0, 3.0, 4.0]))
    my_mat = F.Material(D_0=1, E_D=0, name="mat")
    my_model.subdomains = [
        F.VolumeSubdomain1D(1, borders=[0.0, 4.0], material=my_mat),
    ]
    my_model.species = [F.Species("H")]
    my_model.temperature = 500

    filename = str(tmpdir.join("my_export.xdmf"))
    my_export = F.XDMFExport(filename, field="H")
    my_model.exports = [my_export]
    my_model.settings = F.Settings(atol=1, rtol=0.1)
    my_model.settings.stepsize = F.Stepsize(initial_value=1)

    my_model.initialise()
