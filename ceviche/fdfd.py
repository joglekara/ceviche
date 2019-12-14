import autograd.numpy as npa
import scipy.sparse as sp

from .constants import *
from .primitives import sp_solve, sp_mult, get_entries_indices

# notataion is similar to that used in: http://www.jpier.org/PIERB/pierb36/11.11092006.pdf

class fdfd():
    """ Base class for FDFD simulation """

    def __init__(self, omega, dL, eps_r, npml, bloch_x=0.0, bloch_y=0.0):
        """ initialize with a given structure and source 
                omega: angular frequency (rad/s)
                dL: grid cell size (m)
                eps_r: array containing relative permittivity
                npml: list of number of PML grid cells in [x, y]
                bloch_{x,y} phase difference across {x,y} boundaries for bloch periodic boundary conditions (default = 0 = periodic)
        """

        self.omega = omega
        self.dL = dL
        self.npml = npml

        self.bloch_x = bloch_x
        self.bloch_y = bloch_y

        self.eps_r = eps_r

        self._setup_derivatives()

    """ what happens when you reassign the permittivity of the fdfd object """

    @property
    def eps_r(self):
        """ Returns the relative permittivity grid """
        return self._eps_r

    @eps_r.setter
    def eps_r(self, new_eps):
        """ Defines some attributes when eps_r is set. """
        self._save_shape(new_eps)
        self._eps_r = new_eps

    """ classes inherited from fdfd() must implement their own versions of these functions for `fdfd.solve()` to work """

    def _make_A(self, eps_r):
        """ This method needs to return the indices and elements into the system matrix """        
        raise NotImplementedError("need to make a _make_A() method")

    def _solve_fn(self, entries_a, indices_a, source_vec):
        """ This method needs to return the x, y, and z field components """        
        raise NotImplementedError("need to implement function to solve for field components")

    """ You call this to solve for the electromagnetic fields """

    def solve(self, source_z):
        """ Outward facing function (what gets called by user) that takes a source grid and returns the field components """

        # flatten the permittivity and source grid
        source_vec = self._grid_to_vec(source_z)
        eps_vec = self._grid_to_vec(self.eps_r)

        # create the A matrix for this polarization
        entries_a, indices_a = self._make_A(eps_vec)

        # solve field componets usng A and the source
        Fx_vec, Fy_vec, Fz_vec = self._solve_fn(eps_vec, entries_a, indices_a, source_vec)

        # put all field components into a tuple, convert to grid shape and return them all
        Fx = self._vec_to_grid(Fx_vec)
        Fy = self._vec_to_grid(Fy_vec)
        Fz = self._vec_to_grid(Fz_vec)

        return Fx, Fy, Fz

    """ Utility functions for FDFD object """

    def _setup_derivatives(self):
        """ Makes the sparse derivative matrices and does some processing for ease of use """

        # Creates all of the operators needed for later
        derivs = compute_derivative_matrices(self.omega, self.shape, self.npml, self.dL, bloch_x=self.bloch_x, bloch_y=self.bloch_y)

        # stores the raw sparse matrices
        self.Dxf, self.Dxb, self.Dyf, self.Dyb = derivs

        # store the entries and elements
        self.entries_Dxf, self.indices_Dxf = get_entries_indices(self.Dxf)
        self.entries_Dxb, self.indices_Dxb = get_entries_indices(self.Dxb)
        self.entries_Dyf, self.indices_Dyf = get_entries_indices(self.Dyf)
        self.entries_Dyb, self.indices_Dyb = get_entries_indices(self.Dyb)

        # stores some convenience functions for multiplying derivative matrices by a vector `vec`
        self.mult_Dxf = lambda vec: sp_mult(self.entries_Dxf, self.indices_Dxf, vec)
        self.mult_Dxb = lambda vec: sp_mult(self.entries_Dxb, self.indices_Dxb, vec)
        self.mult_Dyf = lambda vec: sp_mult(self.entries_Dyf, self.indices_Dyf, vec)
        self.mult_Dyb = lambda vec: sp_mult(self.entries_Dyb, self.indices_Dyb, vec)

    def _vec_to_grid(self, vec):
        """ converts a vector quantity into an array of the shape of the FDFD simulation """
        return npa.reshape(vec, self.shape)

    def _grid_to_vec(self, grid):
        """ converts a grid of the shape of the FDFD simulation to a flat vector """
        return grid.flatten()

    def _save_shape(self, grid):
        """ Sores the shape and size of `grid` array to the FDFD object """
        self.shape = grid.shape
        self.Nx, self.Ny = self.shape
        self.N = self.Nx * self.Ny

    @staticmethod
    def _default_val(val, default_val=None):
        # not used yet
        return val if val is not None else default_val

    """ Field conversion functions for 2D.  Function names are self explanatory """

    def _Ex_Ey_to_Hz(self, Ex_vec, Ey_vec):
        return 1 / 1j / MU_0 * (self.mult_Dxb(Ey_vec) - self.mult_Dyb(Ex_vec))

    def _Ez_to_Hx(self, Ez_vec):
        return  1 / 1j / MU_0 * self.mult_Dyb(Ez_vec)

    def _Ez_to_Hy(self, Ez_vec):
        return -1 / 1j / MU_0 * self.mult_Dxb(Ez_vec)

    def _Ex_Ey_to_Hz(self, Ex_vec, Ey_vec):
        return 1 / 1j / MU_0 * (self.mult_Dxb(Ey_vec) - self.mult_Dyb(Ex_vec))

    def _Ez_to_Hx_Hy(self, Ez_vec):
        Hx_vec = self._Ez_to_Hx(Ez_vec)
        Hy_vec = self._Ez_to_Hy(Ez_vec)
        return Hx_vec, Hy_vec

    def _Hz_to_Ex(self, Hz_vec, eps_vec_xx):
        return  1 / 1j / EPSILON_0 / eps_vec_xx * self.mult_Dyf(Hz_vec)

    def _Hz_to_Ey(self, Hz_vec, eps_vec_yy):
        return -1 / 1j / EPSILON_0 / eps_vec_yy * self.mult_Dxf(Hz_vec)

    def _Hx_Hy_to_Ez(self, Hx_vec, Hy_vec, eps_vec_zz):
        return 1 / 1j / EPSILON_0 / eps_vec_zz * (self.mult_Dxf(Hy_vec) - self.mult_Dyf(Hx_vec))

    def _Hz_to_Ex_Ey(self, Hz_vec, eps_vec_xx, eps_vec_yy):
        Ex_vec = self._Hz_to_Ex(Hz_vec, eps_vec_xx)
        Ey_vec = self._Hz_to_Ey(Hz_vec, eps_vec_yy)
        return Ex_vec, Ey_vec

""" These are the fdfd classes that you'll actually want to use """

class fdfd_ez(fdfd):
    """ FDFD class for linear Ez polarization """

    def __init__(self, omega, L0, eps_r, npml, bloch_x=0.0, bloch_y=0.0):
        super().__init__(omega, L0, eps_r, npml, bloch_x=bloch_x, bloch_y=bloch_y)

    def _make_A(self, eps_vec):

        N = eps_vec.size

        C = - 1 / MU_0 * self.Dxf.dot(self.Dxb) \
            - 1 / MU_0 * self.Dyf.dot(self.Dyb)
        entries_c, indices_c = get_entries_indices(C)

        # indices into the diagonal of a sparse matrix
        entries_diag = - EPSILON_0 * self.omega**2 * eps_vec
        indices_diag = npa.vstack((npa.arange(N), npa.arange(N)))

        entries_a = npa.hstack((entries_diag, entries_c))
        indices_a = npa.hstack((indices_diag, indices_c))

        return entries_a, indices_a

    def _solve_fn(self, eps_vec, entries_a, indices_a, Jz_vec):
        Ez_vec = sp_solve(entries_a, indices_a, Jz_vec)
        Hx_vec, Hy_vec = self._Ez_to_Hx_Hy(Ez_vec)
        return Hx_vec, Hy_vec, Ez_vec

class fdfd_hz(fdfd):
    """ FDFD class for linear Ez polarization """

    def __init__(self, omega, L0, eps_r, npml, bloch_x=0.0, bloch_y=0.0):
        super().__init__(omega, L0, eps_r, npml, bloch_x=bloch_x, bloch_y=bloch_y)

    def _grid_average(self, eps_vec):
        eps_grid = self._vec_to_grid(eps_vec)
        eps_grid_xx = 1 / 2 * (eps_grid + npa.roll(eps_grid, axis=1, shift=1))
        eps_grid_yy = 1 / 2 * (eps_grid + npa.roll(eps_grid, axis=0, shift=1))
        eps_vec_xx = self._grid_to_vec(eps_grid_xx)
        eps_vec_yy = self._grid_to_vec(eps_grid_yy)
        return eps_vec_xx, eps_vec_yy

    def _make_A(self, eps_vec):

        # notation: C = [[C11, C12], [C21, C22]]
        C11 = -1 / MU_0 * self.Dyf.dot(self.Dyb) 
        C22 = -1 / MU_0 * self.Dxf.dot(self.Dxb)
        C12 =  1 / MU_0 * self.Dyf.dot(self.Dxb)
        C21 =  1 / MU_0 * self.Dxf.dot(self.Dyb)

        # get entries and indices
        entries_c11, indices_c11 = get_entries_indices(C11)
        entries_c22, indices_c22 = get_entries_indices(C22)
        entries_c12, indices_c12 = get_entries_indices(C12)
        entries_c21, indices_c21 = get_entries_indices(C21)

        # shift the indices into each of the 4 quadrants
        indices_c22 += self.N       # shift into bottom right quadrant
        indices_c12[1,:] += self.N  # shift into top right quadrant
        indices_c21[0,:] += self.N  # shift into bottom left quadrant

        # get full matrix entries and indices
        entries_c = npa.hstack((entries_c11, entries_c12, entries_c21, entries_c22))
        indices_c = npa.hstack((indices_c11, indices_c12, indices_c21, indices_c22))

        # indices into the diagonal of a sparse matrix
        eps_vec_xx, eps_vec_yy = self._grid_average(eps_vec)
        entries_diag = - EPSILON_0 * self.omega**2 * npa.hstack((eps_vec_xx, eps_vec_yy))
        indices_diag = npa.vstack((npa.arange(2 * self.N), npa.arange(2 * self.N)))

        # put together the big A and return entries and indices
        entries_a = npa.hstack((entries_diag, entries_c))
        indices_a = npa.hstack((indices_diag, indices_c))
        return entries_a, indices_a

    def _solve_fn(self, eps_vec, entries_a, indices_a, Mz_vec):

        # convert the Mz current into Jx, Jy
        eps_vec_xx, eps_vec_yy = self._grid_average(eps_vec)
        Jx_vec, Jy_vec = self._Hz_to_Ex_Ey(Mz_vec, eps_vec_xx, eps_vec_yy)

        # lump the current sources together and solve for electric field
        source_J_vec = npa.hstack((Jx_vec, Jy_vec))
        E_vec = sp_solve(entries_a, indices_a, source_J_vec)

        # strip out the x and y components of E and find the Hz component
        Ex_vec = E_vec[:self.N]
        Ey_vec = E_vec[self.N:]
        Hz_vec = self._Ex_Ey_to_Hz(Ex_vec, Ey_vec)

        return Ex_vec, Ey_vec, Hz_vec

"""=========================== HELPER FUNCTIONS ==========================="""

def compute_derivative_matrices(omega, shape, npml, dL, bloch_x=0.0, bloch_y=0.0):

    # make the S-matrices for PML
    (Sxf, Sxb, Syf, Syb) = S_create(omega, shape, npml, dL)

    # Construct derivate matrices without PML
    Dxf_0 = createDws('x', 'f', dL, shape, bloch_x=bloch_x, bloch_y=bloch_y)
    Dxb_0 = createDws('x', 'b', dL, shape, bloch_x=bloch_x, bloch_y=bloch_y)
    Dyf_0 = createDws('y', 'f', dL, shape, bloch_x=bloch_x, bloch_y=bloch_y)
    Dyb_0 = createDws('y', 'b', dL, shape, bloch_x=bloch_x, bloch_y=bloch_y)

    # apply PML to derivative matrices
    Dxf = Sxf.dot(Dxf_0)
    Dxb = Sxb.dot(Dxb_0)
    Dyf = Syf.dot(Dyf_0)
    Dyb = Syb.dot(Dyb_0)

    return Dxf, Dxb, Dyf, Dyb


def S_create(omega, shape, npml, dL):
    # creates S matrices for the PML creation

    Nx, Ny = shape
    N = Nx * Ny
    x_range = [0, float(dL * Nx)]
    y_range = [0, float(dL * Ny)]

    Nx_pml, Ny_pml = npml    

    # Create the sfactor in each direction and for 'f' and 'b'
    s_vector_x_f = create_sfactor('f', omega, dL, Nx, Nx_pml)
    s_vector_x_b = create_sfactor('b', omega, dL, Nx, Nx_pml)
    s_vector_y_f = create_sfactor('f', omega, dL, Ny, Ny_pml)
    s_vector_y_b = create_sfactor('b', omega, dL, Ny, Ny_pml)

    # Fill the 2D space with layers of appropriate s-factors
    Sx_f_2D = npa.zeros(shape, dtype=npa.complex128)
    Sx_b_2D = npa.zeros(shape, dtype=npa.complex128)
    Sy_f_2D = npa.zeros(shape, dtype=npa.complex128)
    Sy_b_2D = npa.zeros(shape, dtype=npa.complex128)

    for i in range(0, Ny):
        Sx_f_2D[:, i] = 1 / s_vector_x_f
        Sx_b_2D[:, i] = 1 / s_vector_x_b

    for i in range(0, Nx):
        Sy_f_2D[i, :] = 1 / s_vector_y_f
        Sy_b_2D[i, :] = 1 / s_vector_y_b

    # Reshape the 2D s-factors into a 1D s-vecay
    Sx_f_vec = Sx_f_2D.reshape((-1,))
    Sx_b_vec = Sx_b_2D.reshape((-1,))
    Sy_f_vec = Sy_f_2D.reshape((-1,))
    Sy_b_vec = Sy_b_2D.reshape((-1,))

    # Construct the 1D total s-vecay into a diagonal matrix
    Sx_f = sp.spdiags(Sx_f_vec, 0, N, N)
    Sx_b = sp.spdiags(Sx_b_vec, 0, N, N)
    Sy_f = sp.spdiags(Sy_f_vec, 0, N, N)
    Sy_b = sp.spdiags(Sy_b_vec, 0, N, N)

    return Sx_f, Sx_b, Sy_f, Sy_b


def createDws(w, s, dL, shape, bloch_x=0.0, bloch_y=0.0):
    """ creates the derivative matrices
            NOTE: python uses C ordering rather than Fortran ordering. Therefore the
            derivative operators are constructed slightly differently than in MATLAB
    """

    Nx, Ny = shape

    if w is 'x':
        if Nx > 1:
            phasor_x = npa.exp(1j * bloch_x)   
            if s is 'f':
                # dxf = sp.diags([-1, 1, 1], [0, 1, -Nx+1], shape=(Nx, Nx))
                dxf = sp.diags([-1, 1, phasor_x], [0, 1, -Nx+1], shape=(Nx, Nx), dtype=npa.complex128)
                Dws = 1 / dL * sp.kron(dxf, sp.eye(Ny))
            else:
                # dxb = sp.diags([1, -1, -1], [0, -1, Nx-1], shape=(Nx, Nx))
                dxb = sp.diags([1, -1, -npa.conj(phasor_x)], [0, -1, Nx-1], shape=(Nx, Nx), dtype=npa.complex128)
                Dws = 1 / dL * sp.kron(dxb, sp.eye(Ny))
        else:
            Dws = sp.eye(Ny)
    if w is 'y':
        if Ny > 1:
            phasor_y = npa.exp(1j * bloch_y)               
            if s is 'f':
                dyf = sp.diags([-1, 1, phasor_y], [0, 1, -Ny+1], shape=(Ny, Ny))
                Dws = 1 / dL * sp.kron(sp.eye(Nx), dyf)
            else:
                dyb = sp.diags([1, -1, -npa.conj(phasor_y)], [0, -1, Ny-1], shape=(Ny, Ny))
                Dws = 1 / dL * sp.kron(sp.eye(Nx), dyb)
        else:
            Dws = sp.eye(Nx)
    return Dws


def sig_w(l, dw, m=3, lnR=-30):
    # helper for S()
    sig_max = -(m + 1) * lnR / (2 * ETA_0 * dw)
    return sig_max * (l / dw)**m


def S(l, dw, omega):
    # helper for create_sfactor()
    return 1 - 1j * sig_w(l, dw) / (omega * EPSILON_0)


def create_sfactor(s, omega, dL, N, N_pml):
    # used to help construct the S matrices for the PML creation

    sfactor_vecay = npa.ones(N, dtype=npa.complex128)
    if N_pml < 1:
        return sfactor_vecay

    dw = N_pml * dL

    for i in range(N):
        if s is 'f':
            if i <= N_pml:
                sfactor_vecay[i] = S(dL * (N_pml - i + 0.5), dw, omega)
            elif i > N - N_pml:
                sfactor_vecay[i] = S(dL * (i - (N - N_pml) - 0.5), dw, omega)
        if s is 'b':
            if i <= N_pml:
                sfactor_vecay[i] = S(dL * (N_pml - i + 1), dw, omega)
            elif i > N - N_pml:
                sfactor_vecay[i] = S(dL * (i - (N - N_pml) - 1), dw, omega)
    return sfactor_vecay

