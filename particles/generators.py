'''
@file matching
@author Kevin Li, Adrian Oeftiger
@date February 2014
@brief Module for matching transverse and longitudinal distributions
@copyright CERN
'''
from __future__ import division

from abc import ABCMeta, abstractmethod

import numpy as np
from numpy.random import RandomState

from scipy.constants import c, e
from scipy.interpolate import interp2d
from scipy.integrate import quad, dblquad, cumtrapz, romb

import pylab as plt


class PhaseSpace(object):
    """Knows how to distribute particle coordinates for a beam
    according to certain distribution functions.
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def generate(self, beam):
        """Creates the beam macroparticles according to a
        distribution function (depends on the implementing class).
        """
        pass


class GaussianX(PhaseSpace):
    """Horizontal Gaussian particle phase space distribution."""

    def __init__(self, sigma_x, sigma_xp, generator_seed=None):
        """Initiates the horizontal beam coordinates
        to the given Gaussian shape.
        """
        self.sigma_x  = sigma_x
        self.sigma_xp = sigma_xp

        self.random_state = RandomState()
        self.random_state.seed(generator_seed)

    @classmethod
    def from_optics(cls, alpha_x, beta_x, epsn_x, betagamma, generator_seed=None):
        """Initialise GaussianX from the given optics functions.
        beta_x is given in meters and epsn_x in micrometers.
        """

        sigma_x  = np.sqrt(beta_x * epsn_x * 1e-6 / betagamma)
        sigma_xp = sigma_x / beta_x

        return cls(sigma_x, sigma_xp, generator_seed)

    def generate(self, beam):
        beam.x = self.sigma_x * self.random_state.randn(beam.n_macroparticles)
        beam.xp = self.sigma_xp * self.random_state.randn(beam.n_macroparticles)


class GaussianY(PhaseSpace):
    """Vertical Gaussian particle phase space distribution."""

    def __init__(self, sigma_y, sigma_yp, generator_seed=None):
        """Initiates the vertical beam coordinates
        to the given Gaussian shape.
        """
        self.sigma_y  = sigma_y
        self.sigma_yp = sigma_yp

        self.random_state = RandomState()
        self.random_state.seed(generator_seed)

    @classmethod
    def from_optics(cls, alpha_y, beta_y, epsn_y, betagamma, generator_seed=None):
        """Initialise GaussianY from the given optics functions.
        beta_y is given in meters and epsn_y in micrometers.
        """

        sigma_y  = np.sqrt(beta_y * epsn_y * 1e-6 / betagamma)
        sigma_yp = sigma_y / beta_y

        return cls(sigma_y, sigma_yp, generator_seed)

    def generate(self, beam):
        beam.y = self.sigma_y * self.random_state.randn(beam.n_macroparticles)
        beam.yp = self.sigma_yp * self.random_state.randn(beam.n_macroparticles)


class GaussianZ(PhaseSpace):
    """Longitudinal Gaussian particle phase space distribution."""

    def __init__(self, sigma_z, sigma_dp, is_accepted = None, generator_seed=None):
        """Initiates the longitudinal beam coordinates to a given
        Gaussian shape. If the argument is_accepted is set to
        the is_in_separatrix(z, dp, beam) method of a RFSystems
        object (or similar), macroparticles will be initialised
        until is_accepted returns True.
        """
        self.sigma_z = sigma_z
        self.sigma_dp = sigma_dp
        self.is_accepted = is_accepted

        self.random_state = RandomState()
        self.random_state.seed(generator_seed)

    @classmethod
    def from_optics(cls, beta_z, epsn_z, p0, is_accepted = None,
                    generator_seed=None):
        """Initialise GaussianZ from the given optics functions.
        For the argument is_accepted see __init__.
        """

        sigma_z = np.sqrt(beta_z*epsn_z/(4*np.pi) * e/p0)
        sigma_dp = sigma_z / beta_z

        return cls(sigma_z, sigma_dp, is_accepted, generator_seed)

    def generate(self, beam):
        beam.z = self.sigma_z * self.random_state.randn(beam.n_macroparticles)
        beam.dp = self.sigma_dp * self.random_state.randn(beam.n_macroparticles)
        if self.is_accepted:
            self._redistribute(beam)

    def _redistribute(self, beam):
        n = beam.n_macroparticles
        for i in xrange(n):
            while not self.is_accepted(beam.z[i], beam.dp[i], beam):
                beam.z[i]  = self.sigma_z * self.random_state.randn(n)
                beam.dp[i] = self.sigma_dp * self.random_state.randn(n)


class RFBucket(PhaseSpace):

    def __init__(self, psi, rfsystem, sigma_z, epsn_z=None):

        self.psi = psi
        self.H = rfsystem
        self.sigma_z = sigma_z

        self.circumference = rfsystem.circumference
        # self.equihamiltonian = rfsystem.equihamiltonian
        self.hamiltonian = rfsystem.hamiltonian
        self.separatrix = rfsystem.separatrix
        self.p_max = rfsystem.p_max
        # self.z_extrema = rfsystem.z_extrema
        # self.z_sep, self.p_sep = rfsystem.z_sep, rfsystem.p_sep
        self.H0 = 1
        self.p0 = rfsystem.p0

        self._compute_std = self._compute_std_cumtrapz
        self.generate = self.dontgenerate

    # @profile
    def _test_maximum_std(self, psi_c, sigma):

        # Test for maximum bunch length
        psi = psi_c.function
        psi_c.H0 = self.H.H0(self.circumference)

        zS = self._compute_std(psi, self.H.separatrix, self.H.zleft, self.H.zright)
        print "\n--> Maximum rms bunch length in bucket:", zS, " m.\n"
        if sigma > zS * 0.95:
            print "\n*** WARNING! Bunch appears to be too long for bucket!\n"


        # # A = self._compute_mean_quad(lambda x, y: 1, self.separatrix, self.z_sep[0], self.z_sep[1])
        # zc = self.z_sep[1]
        # zc = zS
        # zz = plt.linspace(0, self.z_sep[1], 40)
        # A = np.array([self._compute_mean_quad(lambda x, y: 1, self.equihamiltonian(zc), -zc, zc) for zc in zz])
        # print "\n--> Bucket area:", 2 * A * self.p0/e, " eV s.\n"
        # fig, (ax1, ax2, ax3) = plt.subplots(3, figsize=(6, 10))
        # ax1.plot(zz, 2*A*self.p0/e)
        # ax2.plot(zz, self.hamiltonian(zz, 0))
        # ax3.plot(self.hamiltonian(zz, 0), 2*A*self.p0/e)
        # plt.show()
        # exit(-1)


        # zS = self._compute_std_quad(psi.function, self.separatrix, self.z_sep[0], self.z_sep[1])
        # print "\n--> Maximum rms bunch length in bucket:", zS, " m.\n"
        # if sigma > zS * 0.95:
        #     print "\n*** WARNING! Bunch appears to be too long for bucket!\n"

        # zS = self._compute_std_cumtrapz(psi.function, self.separatrix, self.z_sep[0], self.z_sep[1])
        # print "\n--> Maximum rms bunch length in bucket:", zS, " m.\n"
        # if sigma > zS * 0.95:
        #     print "\n*** WARNING! Bunch appears to be too long for bucket!\n"

        # zS = self._compute_std_romberg(psi.function, self.separatrix, self.z_sep[0], self.z_sep[1])
        # print "\n--> Maximum rms bunch length in bucket:", zS, " m.\n"
        # if sigma > zS * 0.95:
        #     print "\n*** WARNING! Bunch appears to be too long for bucket!\n"

    def psi_for_emittance(self, epsn_z):

        zz = np.linspace(self.H.zs + np.abs(self.H.zs)*0.01, self.H.zright - np.abs(self.H.zright)*0.01, 10)

        A = []
        for zc in zz:
            zleft, zright = self.H.get_z_left_right(zc)
            A.append( self._compute_mean_quad(lambda y, x: 1, self.H.equihamiltonian(zc), zleft, zright) * 2*self.p0/e )
        A = np.array(A)

        a = epsn_z
        ix = np.where(np.diff(np.sign(A-a)))[0]
        m = (A[ix+1] - A[ix])/(zz[ix+1] - zz[ix])
        dy = a - A[ix]
        b = zz[ix] + dy/m
        # print b
        # plt.figure(12)
        # plt.plot(zz, A)
        # plt.plot(b, a, '+', ms=12, mew=4)
        # plt.grid()
        # plt.show()

        return b

    def psi_for_bunchlength(self, sigma):

        H = self.H
        psi_c =  self.psi(H.hamiltonian, H.Hmax)
        psi = psi_c.function

        self._test_maximum_std(psi_c, sigma)

        fw = self.H.zright-self.H.zs
        zz = np.linspace(fw*0.05, fw*0.95, 10)

        L = []
        for i, zc in enumerate(zz):
            psi_c.H0 = self.H.H0(zc)
            print i+1, psi_c.H0
            L.append( self._compute_std(psi, H.separatrix, H.zleft, H.zright) )
        L = np.array(L)

        l = sigma
        ix = np.where(np.diff(np.sign(L-l)))[0]
        m = (L[ix+1] - L[ix])/(zz[ix+1] - zz[ix])
        dy = l - L[ix]
        k = zz[ix] + dy/m
        psi_c.H0 = self.H.H0(k)

        xx, pp = np.linspace(H.zleft, H.zright, 200), np.linspace(-H.p_max(H.zright), H.p_max(H.zright), 200)
        XX, PP = np.meshgrid(xx, pp)
        fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 6))
        ax3 = fig.add_subplot(133, projection='3d')
        ax1.plot(zz, L)
        ax1.axhline(l, c='r', lw=2)
        ax1.plot(k, l, '+', ms=12, mew=4)
        ax1.grid()
        ax2.plot(xx, psi(xx, 0))
        ax3.plot_surface(XX, PP, psi(XX, PP), cmap=plt.cm.jet)
        plt.show()

        return psi

    def _set_target_std(self, psi, sigma):

        self._test_maximum_std(psi, sigma)
        psi.Hmax = np.amax(self.hamiltonian(self.z_extrema, 0))

        print 'Iterative evaluation of bunch length...'
        counter = 0
        z0 = sigma
        eps = 1

        # Iteratively obtain true H0 to make target sigma
        zH = z0
        psi.H0 = self.H0(zH)
        a = 1
        while abs(eps)>1e-4:
            zS = self._compute_std(psi.function, self.separatrix, self.z_sep[0], self.z_sep[1])

            # TODO: optimize convergence algorithm: particle swarm optimization
            eps = zS - z0
            print counter, zH, zS, eps
            zH -= a * eps
            psi.H0 = self.H0(zH)

            counter += 1
            if counter > 100:
                print "\n*** WARNING: too many interation steps! There are several possible reasons for that:"
                print "1. Is the Hamiltonian correct?"
                print "2. Is the stationary distribution function convex around zero?"
                print "3. Is the bunch too long to fit into the bucket?"
                print "4. Is this algorithm not qualified?"
                print "Aborting..."
                sys.exit(-1)
            elif counter > 90:
                a = 0.1
            elif counter > 60:
                a = 0.25
            elif counter > 30:
                a = 0.5

        print "*** Converged!\n"

        return psi.function

    def _compute_mean_quad(self, psi, p_sep, xmin, xmax):
        '''
        Compute the variance of the distribution function psi from xmin to xmax
        along the contours p_sep using numerical integration methods.
        '''
        # plt.ion()
        # fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 8))
        # ax3 = fig.add_subplot(133, projection='3d')
        # xx = np.linspace(xmin, xmax, 1000)
        # yy = np.linspace(-self.p_sep, self.p_sep, 1000)
        # XX, YY = np.meshgrid(xx, yy)
        # PP = psi(XX, YY)
        # ax1.plot(xx, p_sep(xx))
        # ax1.plot(xx, -p_sep(xx))
        # ax2.plot(xx, psi(xx, 0))
        # ax3.cla()
        # ax3.plot_surface(XX, YY, PP, cstride=100, rstride=100, cmap=plt.cm.jet)
        # # plt.draw()
        # plt.show()

        Q, error = dblquad(lambda y, x: psi(x, y), xmin, xmax,
                    lambda x: 0, lambda x: p_sep(x))

        return Q

    def _compute_std_quad(self, psi, p_sep, xmin, xmax):
        '''
        Compute the variance of the distribution function psi from xmin to xmax
        along the contours p_sep using numerical integration methods.
        '''
        # # plt.ion()
        # fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 8))
        # ax3 = fig.add_subplot(133, projection='3d')
        # xx = np.linspace(xmin, xmax, 1000)
        # yy = np.linspace(-self.p_max(xmax), self.p_max(xmax), 1000)
        # XX, YY = np.meshgrid(xx, yy)
        # PP = psi(XX, YY)
        # ax1.plot(xx, p_sep(xx))
        # ax1.plot(xx, -p_sep(xx))
        # ax2.plot(xx, psi(xx, 0))
        # ax3.cla()
        # ax3.plot_surface(XX, YY, PP, cstride=100, rstride=100, cmap=plt.cm.jet)
        # # plt.draw()
        # plt.show()

        Q, error = dblquad(lambda y, x: psi(x, y), xmin, xmax,
                    lambda x: 0, lambda x: p_sep(x))
        V, error = dblquad(lambda y, x: x ** 2 * psi(x, y), xmin, xmax,
                    lambda x: 0, lambda x: p_sep(x))

        return np.sqrt(V/Q)

    def _compute_std_cumtrapz(self, psi, p_sep, xmin, xmax):
        '''
        Compute the variance of the distribution function psi from xmin to xmax
        along the contours p_sep using numerical integration methods.
        '''

        x_arr = np.linspace(xmin, xmax, 257)
        dx = x_arr[1] - x_arr[0]

        Q, V = 0, 0
        for x in x_arr:
            y = np.linspace(0, p_sep(x), 257)
            z = psi(x, y)
            Q += cumtrapz(z, y)[-1]
            z = x**2 * psi(x, y)
            V += cumtrapz(z, y)[-1]
        Q *= dx
        V *= dx

        return np.sqrt(V/Q)

    def _compute_std_romberg(self, psi, p_sep, xmin, xmax):
        '''
        Compute the variance of the distribution function psi from xmin to xmax
        along the contours p_sep using numerical integration methods.
        '''

        x_arr = np.linspace(xmin, xmax, 257)
        dx = x_arr[1] - x_arr[0]

        Q, V = 0, 0
        for x in x_arr:
            y = np.linspace(0, p_sep(x), 257)
            dy = y[1] - y[0]
            z = psi(x, y)
            Q += romb(z, dy)
            z = x**2 * psi(x, y)
            V += romb(z, dy)
        Q *= dx
        V *= dx

        return np.sqrt(V/Q)

    def dontgenerate(self, particles):

        particles.z = np.zeros(particles.n_macroparticles)
        particles.dp = np.zeros(particles.n_macroparticles)
        particles.generator = self

    def generate(self, particles):
        '''
        Generate a 2d phase space of n_particles particles randomly distributed
        according to the particle distribution function psi within the region
        [xmin, xmax, ymin, ymax].
        '''
        psi = self._set_target_std(StationaryExponential(self.hamiltonian), self.sigma_z)

        x = np.zeros(particles.n_macroparticles)
        y = np.zeros(particles.n_macroparticles)

        # Bin
        i, j = 0, 0
        nx, ny = 128, 128
        xmin, xmax = self.z_sep[0], self.z_sep[1]
        ymin, ymax = -self.p_sep, self.p_sep
        lx = (xmax - xmin)
        ly = (ymax - ymin)

        xx = np.linspace(xmin, xmax, nx + 1)
        yy = np.linspace(ymin, ymax, ny + 1)
        XX, YY = np.meshgrid(xx, yy)
        HH = psi(XX, YY)
        psi_interp = interp2d(xx, yy, HH)

        while j < particles.n_macroparticles:
            u = xmin + lx * np.random.random()
            v = ymin + ly * np.random.random()

            s = np.random.random()

            i += 1
            if s < psi_interp(u, v):
                x[j] = u
                y[j] = v
                # TODO: check if this does not cause problems! Setter for item does not work - not implemented!
                # particles.dp[j] = v
                j += 1

        particles.z = x
        particles.dp = y
        particles.psi = psi
        # return x, y, j / i * dx * dy, psi


class UniformX(PhaseSpace):
    """
    Horizontal uniform particle phase space distribution.
    """

    def __init__(self, x_min, x_max):

        self.x_min, self.x_max = x_min, x_max

    def generate(self, particles):
        dx = self.x_max - self.x_min
        particles.x = self.x_min + np.random.rand(particles.n_macroparticles) * dx
        particles.xp = 0. * particles.x


class UniformY(PhaseSpace):
    """
    Vertical uniform particle phase space distribution.
    """

    def __init__(self, y_min, y_max):

        self.y_min, self.y_max = y_min, y_max

    def generate(self, particles):
        dy = self.y_max - self.y_min
        particles.y = self.y_min + np.random.rand(particles.n_macroparticles) * dy
        particles.yp = 0. * particles.y


class UniformZ(PhaseSpace):
    """
    Longitudinal uniform particle phase space distribution.
    """

    def __init__(self, z_min, z_max):

        self.z_min, self.z_max = z_min, z_max

    def generate(self, particles):
        dz = self.z_max - self.z_min
        particles.z = self.z_min + np.random.rand(particles.n_macroparticles) * dz
        particles.dp = 0. * particles.z


class ImportX(PhaseSpace):

    def __init__(x, xp):

        self.x = x
        self.xp = xp

    def generate(self, particles):

        assert(particles.n_particles == len(self.x) == len(self.xp))
        particles.x = self.x.copy()
        particles.xp = self.xp.copy()


class ImportY(PhaseSpace):

    def __init__(y, yp):

        self.y = y
        self.yp = yp

    def generate(self, particles):

        assert(particles.n_particles == len(self.y) == len(self.yp))
        particles.y = self.y.copy()
        particles.yp = self.yp.copy()


class ImportZ(PhaseSpace):

    def __init__(z, dp):

        self.z = z
        self.dp = dp

    def generate(self, particles):

        assert(particles.n_particles == len(self.z) == len(self.dp))
        particles.z = self.z.copy()
        particles.dp = self.dp.copy()


class StationaryExponential(object):

    def __init__(self, H, Hmax=None, width=1000, Hcut=0):
        self.H = H
        self.H0 = 1
        if not Hmax:
            self.Hmax = H(0, 0)
        else:
            self.Hmax = Hmax
        self.Hcut = Hcut
        self.width = width

    def function(self, z, dp):
        # psi = np.exp((self.H(z, dp)) / (self.width*self.Hmax)) - 1
        # psi_offset = np.exp(self.Hcut / (self.width*self.Hmax)) - 1
        # psi_norm = (np.exp(1/self.width) - 1) - psi_offset
        # return ( (psi-psi_offset) / psi_norm ).clip(min=0)

        # psi = np.exp( (self.H(z, dp)-self.Hcut).clip(min=0) / (self.width*self.Hmax)) - 1
        # psi_norm = np.exp( (self.Hmax-0*self.Hcut) / (self.width*self.Hmax) ) - 1
        # psi = np.exp( -self.H(z, dp).clip(min=0)/(self.width*self.Hmax) ) - 1
        # psi_norm = np.exp( -self.Hmax/(self.width*self.Hmax) ) - 1
        psi = np.exp(self.H(z, dp).clip(min=0)/self.H0) - 1
        psi_norm = np.exp(self.Hmax/self.H0) - 1
        return psi/psi_norm