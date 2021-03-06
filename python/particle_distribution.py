"""
Analysis procedures for particle energy spectrum.
"""
import collections
import itertools
import math
import multiprocessing
import os
import os.path
import struct
import subprocess
import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import scipy
from joblib import Parallel, delayed
from matplotlib import rc
from matplotlib.colors import LogNorm
from matplotlib.ticker import MaxNLocator
# from mpi4py import MPI
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.mplot3d import Axes3D
from scipy import interpolate, signal

import color_maps as cm
import colormap.colormaps as cmaps
import pic_information
from contour_plots import plot_2d_contour, read_2d_fields
from energy_conversion import read_data_from_json
from shell_functions import mkdir_p
from spectrum_fitting import get_energy_distribution

# import particle_spectrum_vdist as psv

rc('font', **{'family': 'serif', 'serif': ['Computer Modern']})
mpl.rc('text', usetex=True)
mpl.rcParams['text.latex.preamble'] = [r"\usepackage{amsmath}"]

font = {
    'family': 'serif',
    #'color'  : 'darkred',
    'color': 'black',
    'weight': 'normal',
    'size': 24,
}


class cd:
    """Context manager for changing the current working directory"""

    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)


def read_boilerplate(fh):
    """Read boilerplate of a file

    Args:
        fh: file handler
    """
    offset = 0
    sizearr = np.memmap(
        fh, dtype='int8', mode='r', offset=offset, shape=(5), order='F')
    offset += 5
    cafevar = np.memmap(
        fh, dtype='int16', mode='r', offset=offset, shape=(1), order='F')
    offset += 2
    deadbeefvar = np.memmap(
        fh, dtype='int32', mode='r', offset=offset, shape=(1), order='F')
    offset += 4
    realone = np.memmap(
        fh, dtype='float32', mode='r', offset=offset, shape=(1), order='F')
    offset += 4
    doubleone = np.memmap(
        fh, dtype='float64', mode='r', offset=offset, shape=(1), order='F')


def read_particle_header(fh):
    """Read particle file header

    Args:
        fh: file handler.
    """
    offset = 23  # the size of the boilerplate is 23
    tmp1 = np.memmap(
        fh, dtype='int32', mode='r', offset=offset, shape=(6), order='F')
    offset += 6 * 4
    tmp2 = np.memmap(
        fh, dtype='float32', mode='r', offset=offset, shape=(10), order='F')
    offset += 10 * 4
    tmp3 = np.memmap(
        fh, dtype='int32', mode='r', offset=offset, shape=(4), order='F')
    v0header = collections.namedtuple("v0header", [
        "version", "type", "nt", "nx", "ny", "nz", "dt", "dx", "dy", "dz",
        "x0", "y0", "z0", "cvac", "eps0", "damp", "rank", "ndom", "spid",
        "spqm"
    ])
    v0 = v0header(
        version=tmp1[0],
        type=tmp1[1],
        nt=tmp1[2],
        nx=tmp1[3],
        ny=tmp1[4],
        nz=tmp1[5],
        dt=tmp2[0],
        dx=tmp2[1],
        dy=tmp2[2],
        dz=tmp2[3],
        x0=tmp2[4],
        y0=tmp2[5],
        z0=tmp2[6],
        cvac=tmp2[7],
        eps0=tmp2[8],
        damp=tmp2[9],
        rank=tmp3[0],
        ndom=tmp3[1],
        spid=tmp3[2],
        spqm=tmp3[3])
    header_particle = collections.namedtuple("header_particle",
                                             ["size", "ndim", "dim"])
    offset += 4 * 4
    tmp4 = np.memmap(
        fh, dtype='int32', mode='r', offset=offset, shape=(3), order='F')
    pheader = header_particle(size=tmp4[0], ndim=tmp4[1], dim=tmp4[2])
    offset += 3 * 4
    return (v0, pheader, offset)


def read_particle_data(fname):
    """Read particle information from a file.

    Args:
        fname: file name.
    """
    fh = open(fname, 'r')
    read_boilerplate(fh)
    v0, pheader, offset = read_particle_header(fh)
    nptl = pheader.dim
    particle_type = np.dtype([('dxyz', np.float32, 3), ('icell', np.int32),
                              ('u', np.float32, 3), ('q', np.float32)])
    fh.seek(offset, os.SEEK_SET)
    data = np.fromfile(fh, dtype=particle_type, count=nptl)
    fh.close()
    return (v0, pheader, data)


def calc_velocity_distribution(v0,
                               pheader,
                               ptl,
                               pic_info,
                               corners,
                               nbins,
                               ptl_mass=1,
                               pmax=1.0):
    """Calculate particle velocity distribution

    Args:
        v0: the header info for the grid.
        pheader: the header info for the particles.
        pic_info: namedtuple for the PIC simulation information.
        corners: the corners of the box in di.
        nbins: number of bins in each dimension.
    """
    dx = ptl['dxyz'][:, 0]
    dy = ptl['dxyz'][:, 1]
    dz = ptl['dxyz'][:, 2]
    icell = ptl['icell']
    ux = ptl['u'][:, 0] * ptl_mass
    uy = ptl['u'][:, 1] * ptl_mass
    uz = ptl['u'][:, 2] * ptl_mass

    nx = v0.nx + 2
    ny = v0.ny + 2
    nz = v0.nz + 2
    iz = icell // (nx * ny)
    iy = (icell - iz * nx * ny) // nx
    ix = icell - iz * nx * ny - iy * nx

    z = v0.z0 + ((iz - 1.0) + (dz + 1.0) * 0.5) * v0.dz
    y = v0.y0 + ((iy - 1.0) + (dy + 1.0) * 0.5) * v0.dy
    x = v0.x0 + ((ix - 1.0) + (dx + 1.0) * 0.5) * v0.dx

    # de -> di
    smime = math.sqrt(pic_info.mime)
    x /= smime
    y /= smime
    z /= smime

    mask = ((x >= corners[0][0]) & (x <= corners[0][1]) &
            (y >= corners[1][0]) & (y <= corners[1][1]) &
            (z >= corners[2][0]) & (z <= corners[2][1]))
    ux_d = ux[mask]
    uy_d = uy[mask]
    uz_d = uz[mask]

    # Assumes that magnetic field is along the z-direction
    upara = uz_d
    uperp = np.sqrt(ux_d * ux_d + uy_d * uy_d)
    upara_abs = np.abs(uz_d)
    utot = np.sqrt(ux_d * ux_d + uy_d * uy_d + uz_d * uz_d)

    drange = [[-pmax, pmax], [-pmax, pmax]]
    hist_xy, ubins_edges, ubins_edges = np.histogram2d(
        uy_d, ux_d, bins=nbins, range=drange)
    hist_xz, ubins_edges, ubins_edges = np.histogram2d(
        uz_d, ux_d, bins=nbins, range=drange)
    hist_yz, ubins_edges, ubins_edges = np.histogram2d(
        uz_d, uy_d, bins=nbins, range=drange)
    drange = [[-pmax, pmax], [0, pmax]]
    hist_para_perp, upara_edges, uperp_edges = np.histogram2d(
        upara, uperp, bins=[nbins, nbins / 2], range=drange)

    # 1D
    pmin = 1E-4
    pmin_log, pmax_log = math.log10(pmin), math.log10(pmax)
    pbins_log = 10**np.linspace(pmin_log, pmax_log, nbins)
    ppara_dist, pedge = np.histogram(upara_abs, bins=pbins_log)
    pperp_dist, pedge = np.histogram(uperp, bins=pbins_log)
    pdist, pedge = np.histogram(utot, bins=pbins_log)

    hists = {
        'hist_xy': hist_xy,
        'hist_xz': hist_xz,
        'hist_yz': hist_yz,
        'hist_para_perp': hist_para_perp,
        'ppara_dist': ppara_dist,
        'pperp_dist': pperp_dist,
        'pdist': pdist
    }
    bins = {
        'pbins_long': ubins_edges,
        'pbins_short': uperp_edges,
        'pbins_log': pbins_log
    }

    return (hists, bins)


def get_particle_distribution(base_dir, pic_info, tindex, corners, mpi_ranks):
    """Read particle information.

    Args:
        base_dir: the base directory for the simulation data.
        tindex: the time index.
        corners: the corners of the box in di.
        mpi_ranks: PIC simulation MPI ranks for a selected region.
    """
    dir_name = base_dir + 'particle/T.' + str(tindex) + '/'
    fbase = dir_name + 'eparticle' + '.' + str(tindex) + '.'
    tx = pic_info.topology_x
    ty = pic_info.topology_y
    tz = pic_info.topology_z
    nbins = 64
    hist_xy = np.zeros((nbins, nbins))
    hist_xz = np.zeros((nbins, nbins))
    hist_yz = np.zeros((nbins, nbins))
    mpi_ranks = np.asarray(mpi_ranks)
    for ix in range(mpi_ranks[0, 0], mpi_ranks[0, 1] + 1):
        for iy in range(mpi_ranks[1, 0], mpi_ranks[1, 1] + 1):
            for iz in range(mpi_ranks[2, 0], mpi_ranks[2, 1] + 1):
                mpi_rank = ix + iy * tx + iz * tx * ty
                fname = fbase + str(mpi_rank)
                (v0, pheader, data) = read_particle_data(fname)
                hists, bins = calc_velocity_distribution(
                    v0, pheader, data, pic_info, corners, nbins)
                hist_xy += hists['hist_xy']
                hist_xz += hists['hist_xz']
                hist_yz += hists['hist_yz']
    pbins = bins['pbins_long']
    pmin = pbins[0]
    pmax = pbins[-1]
    u1, u2 = np.meshgrid(pbins[:-1], pbins[:-1])
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    hist_xy = signal.convolve2d(hist_xy, kernel, 'same')
    hist_xz = signal.convolve2d(hist_xz, kernel, 'same')
    hist_yz = signal.convolve2d(hist_yz, kernel, 'same')
    print u1.shape, u2.shape, hist_xy.shape
    fxy = interpolate.interp2d(u1, u2, np.log10(hist_xy + 0.5), kind='cubic')
    fxz = interpolate.interp2d(u1, u2, np.log10(hist_xz + 0.5), kind='cubic')
    fyz = interpolate.interp2d(u1, u2, np.log10(hist_yz + 0.5), kind='cubic')
    unew = np.linspace(-1.0, 1.0, 200)
    fxy_new = fxy(unew, unew)
    fxz_new = fxz(unew, unew)
    fyz_new = fyz(unew, unew)

    fxy = fxy_new
    fxz = fxz_new
    fyz = fyz_new

    vmax = np.max([np.max(hist_xy), np.max(hist_xz), np.max(hist_yz)])
    vmax = math.log10(vmax)
    xs, ys = 0.08, 0.17
    w1, h1 = 0.24, 0.72
    gap = 0.08
    fig = plt.figure(figsize=(12, 4))
    ax1 = fig.add_axes([xs, ys, w1, h1])
    p1 = ax1.imshow(
        fxy_new,
        cmap=plt.cm.jet,
        extent=[pmin, pmax, pmin, pmax],
        aspect='auto',
        origin='lower',
        vmin=0.0,
        vmax=vmax)
    # interpolation='bicubic')
    ax1.set_xlabel(r'$u_x$', fontdict=font, fontsize=20)
    ax1.set_ylabel(r'$u_y$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)
    xs += w1 + gap
    ax2 = fig.add_axes([xs, ys, w1, h1])
    p2 = ax2.imshow(
        fxz_new,
        cmap=plt.cm.jet,
        extent=[pmin, pmax, pmin, pmax],
        aspect='auto',
        origin='lower',
        vmin=0.0,
        vmax=vmax)
    ax2.set_xlabel(r'$u_x$', fontdict=font, fontsize=20)
    ax2.set_ylabel(r'$u_z$', fontdict=font, fontsize=20)
    ax2.tick_params(labelsize=16)
    xs += w1 + gap
    ax3 = fig.add_axes([xs, ys, w1, h1])
    p3 = ax3.imshow(
        fyz_new,
        cmap=plt.cm.jet,
        extent=[pmin, pmax, pmin, pmax],
        aspect='auto',
        origin='lower',
        vmin=0.0,
        vmax=vmax)
    # interpolation='bicubic')
    ax3.set_xlabel(r'$u_y$', fontdict=font, fontsize=20)
    ax3.set_ylabel(r'$u_z$', fontdict=font, fontsize=20)
    ax3.tick_params(labelsize=16)
    p1.set_cmap(plt.cm.get_cmap('hot'))
    p2.set_cmap(plt.cm.get_cmap('hot'))
    p3.set_cmap(plt.cm.get_cmap('hot'))
    plt.show()


def get_phase_distribution(base_dir, pic_info, species, tindex, corners,
                           mpi_ranks):
    """Get particle phase space distributions

    Args:
        base_dir: the base directory for the simulation data.
        tindex: the time index.
        corners: the corners of the box in di.
        mpi_ranks: PIC simulation MPI ranks for a selected region.
    """
    dir_name = base_dir + 'particles/T.' + str(tindex) + '/'
    fbase = dir_name + species + '.' + str(tindex) + '.'
    tx = pic_info.topology_x
    ty = pic_info.topology_y
    tz = pic_info.topology_z
    nbins = 128
    hist_xy = np.zeros((nbins, nbins))
    hist_xz = np.zeros((nbins, nbins))
    hist_yz = np.zeros((nbins, nbins))
    hist_para_perp = np.zeros((nbins, nbins / 2))
    ppara_dist = np.zeros(nbins - 1)
    pperp_dist = np.zeros(nbins - 1)
    pdist = np.zeros(nbins - 1)
    mpi_ranks = np.asarray(mpi_ranks)
    if species == 'electron':
        ptl_mass = 1
        pmax = 4.0
    else:
        ptl_mass = pic_info.mime
        pmax = 40.0
    for ix in range(mpi_ranks[0, 0], mpi_ranks[0, 1] + 1):
        for iy in range(mpi_ranks[1, 0], mpi_ranks[1, 1] + 1):
            for iz in range(mpi_ranks[2, 0], mpi_ranks[2, 1] + 1):
                mpi_rank = ix + iy * tx + iz * tx * ty
                fname = fbase + str(mpi_rank)
                (v0, pheader, data) = read_particle_data(fname)
                hists, bins = calc_velocity_distribution(v0, pheader, data,
                                                         pic_info, corners,
                                                         nbins, ptl_mass, pmax)
                hist_xy += hists['hist_xy']
                hist_xz += hists['hist_xz']
                hist_yz += hists['hist_yz']
                hist_para_perp += hists['hist_para_perp']
                ppara_dist += hists['ppara_dist']
                pperp_dist += hists['pperp_dist']
                pdist += hists['pdist']

    pbins_lin_long = bins['pbins_long']
    pbins_lin_short = bins['pbins_short']
    pbins_log = bins['pbins_log']
    pmin = pbins_lin_long[0]
    pmax = pbins_lin_long[-1]
    dp = pbins_lin_long[1] - pbins_lin_long[0]
    hist_para_perp /= np.sum(hist_para_perp) * dp

    if species is 'ion':
        vmin, vmax = 1E-6, 1E-1
    else:
        vmin, vmax = 1E-6, 1E-1
    xs, ys = 0.09, 0.15
    w1, h1 = 0.8, 0.8
    gap = 0.08
    fig1 = plt.figure(figsize=(8, 4))
    ax1 = fig1.add_axes([xs, ys, w1, h1])
    p1 = ax1.imshow(
        hist_para_perp.T,
        cmap=plt.cm.jet,
        extent=[pmin, pmax, 0, pmax],
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=vmin, vmax=vmax))
    xs1 = xs + w1 + 0.02
    cax = fig1.add_axes([xs1, ys, 0.02, h1])
    cbar = fig1.colorbar(p1, cax=cax)
    cbar.ax.tick_params(labelsize=16)
    ax1.set_xlabel(r'$p_\parallel$', fontdict=font, fontsize=20)
    ax1.set_ylabel(r'$p_\perp$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)

    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    fig2 = plt.figure(figsize=(7, 5))
    ax1 = fig2.add_axes([xs, ys, w1, h1])
    pintervals = np.diff(pbins_log)
    ax1.loglog(
        pbins_log[:-1],
        ppara_dist / pintervals,
        color='r',
        linewidth=2,
        label=r'$f(p_\parallel)$')
    ax1.loglog(
        pbins_log[:-1],
        pperp_dist / pintervals,
        color='b',
        linewidth=2,
        label=r'$f(p_\perp)$')
    ax1.loglog(
        pbins_log[:-1],
        pdist / pintervals,
        color='k',
        linewidth=2,
        label=r'$f(p)$')
    leg = ax1.legend(
        loc=3,
        prop={'size': 20},
        ncol=1,
        shadow=False,
        fancybox=False,
        frameon=False)
    if species == 'electron':
        ax1.set_xlim([1E-4, 1E1])
        ax1.set_ylim([1E3, 1E10])
    else:
        ax1.set_xlim([1E-3, 1E2])
        ax1.set_ylim([1E2, 1E9])
    ax1.set_xlabel(r'$p_\parallel, p_\perp, p$', fontdict=font, fontsize=20)
    ax1.set_ylabel(r'$f$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)

    return (fig1, fig2)
    # plt.show()


def set_mpi_ranks(pic_info, center=np.zeros(3), sizes=[400, 400, 400]):
    """Set MPI ranks for getting particle data

    Args:
        pic_info: namedtuple for the PIC simulation information.
        center: the center of a box in di.
        sizes: the sizes of the box in grids.
    Returns:
        corners: the corners of the box in di.
        mpi_ranks: MPI ranks in which the box is.
    """
    # The domain sizes for each MPI process (in di)
    dx_domain = pic_info.lx_di / pic_info.topology_x
    dy_domain = pic_info.ly_di / pic_info.topology_y
    dz_domain = pic_info.lz_di / pic_info.topology_z
    lx_di = pic_info.lx_di
    ly_di = pic_info.ly_di
    lz_di = pic_info.lz_di

    # The sizes of each cell
    dx_di = pic_info.dx_di
    dy_di = pic_info.dy_di
    dz_di = pic_info.dz_di
    sizes = np.asarray(sizes)
    hsize = sizes / 2.0
    xs = center[0] - hsize[0] * dx_di
    xe = center[0] + hsize[0] * dx_di
    ys = center[1] - hsize[1] * dy_di
    ye = center[1] + hsize[1] * dy_di
    zs = center[2] - hsize[2] * dz_di
    ze = center[2] + hsize[2] * dz_di

    # x in [0, lx_di], y in [-ly_di/2, ly_di/2], z in [-lz_di/2, lz_di/2]
    if (xs < 0): xs = 0.0
    if (xs > lx_di): xs = lx_di
    if (xe < 0): xe = 0.0
    if (xe > lx_di): xe = lx_di
    if (ys < -ly_di * 0.5): ys = -ly_di * 0.5
    if (ys > ly_di * 0.5): ys = ly_di * 0.5
    if (ye < -ly_di * 0.5): ye = -ly_di * 0.5
    if (ye > ly_di * 0.5): ye = ly_di * 0.5
    if (zs < -lz_di * 0.5): zs = -lz_di * 0.5
    if (zs > lz_di * 0.5): zs = lz_di * 0.5
    if (ze < -lz_di * 0.5): ze = -lz_di * 0.5
    if (ze > lz_di * 0.5): ze = lz_di * 0.5

    ixs = int(math.floor(xs / dx_domain))
    ixe = int(math.floor(xe / dx_domain))
    iys = int(math.floor((ys + ly_di * 0.5) / dy_domain))
    iye = int(math.floor((ye + ly_di * 0.5) / dy_domain))
    izs = int(math.floor((zs + lz_di * 0.5) / dz_domain))
    ize = int(math.floor((ze + lz_di * 0.5) / dz_domain))
    if (ixe >= pic_info.topology_x):
        ixe = pic_info.topology_x - 1
    if (iye >= pic_info.topology_y):
        iye = pic_info.topology_y - 1
    if (ize >= pic_info.topology_z):
        ize = pic_info.topology_z - 1

    corners = np.zeros((3, 2))
    mpi_ranks = np.zeros((3, 2))
    corners = [[xs, xe], [ys, ye], [zs, ze]]
    mpi_ranks = [[ixs, ixe], [iys, iye], [izs, ize]]
    return (corners, mpi_ranks)


def generate_spectrum_vdist_config(fname, **kwargs):
    """Generate spectrum and velocity distribution configuration

    Args:
        fname: filename of the configuration file.
    """
    with open(fname, 'w+') as f:
        center = kwargs['center']
        sizes = kwargs['sizes']
        f.write('***** Configuration file for velocity distribution *****\n')
        f.write('\n')
        f.write('nbins = 600\n')
        f.write('emax = 100.0\n')
        f.write('emin = 0.0001\n')
        f.write('xc/de = %6.2f\n' % center[0])
        f.write('yc/de = %6.2f\n' % center[1])
        f.write('zc/de = %6.2f\n' % center[2])
        f.write('xsize = %d\n' % sizes[0])
        f.write('ysize = %d\n' % sizes[1])
        f.write('zsize = %d\n' % sizes[2])
        f.write('nbins_vdist = %d\n' % kwargs['nbins'])
        f.write('vmax = %6.2f\n' % kwargs['vmax'])
        f.write('vmin = %6.2f\n' % kwargs['vmin'])
        f.write('tframe = %d\n' % kwargs['tframe'])
        f.close()


def get_spectrum_vdist(pic_info,
                       fdir='../',
                       config_name='config_files/vdist_config.dat',
                       **kwargs):
    """Get particle spectra and velocity distributions
    """
    fname = fdir + config_name
    generate_spectrum_vdist_config(fname, **kwargs)
    # cmd = './particle_spectrum_vdist_box ' + config_name
    # p1 = subprocess.Popen([cmd], cwd='../', shell=True)
    # cmd = 'mpirun -np 16 python particle_spectrum_vdist.py ' + config_name
    cmd = 'mpirun -np 16 particle_spectrum_vdist_box ' + \
            '-c ' + config_name + ' -s ' + kwargs['species']
    print cmd
    p1 = subprocess.Popen(
        [cmd],
        cwd=fdir,
        stdout=open('outfile.out', 'w'),
        stderr=subprocess.STDOUT,
        shell=True)
    p1.wait()
    # with cd('../'):
    #     psv.particle_spectrum_vdist_box()


def read_velocity_distribution(species,
                               tframe,
                               pic_info,
                               fname_1d,
                               fname_2d,
                               fpath='../vdistributions/'):
    """Read velocity distribution from a file.

    Args:
        fpath: file path for the data.
        species: particle species.
        tframe: time frame.
        pic_info: particle information namedtuple.
    """
    # 2D distributions
    f = open(fpath + fname_2d, 'r')
    center = np.zeros(3)
    sizes = np.zeros(3)
    offset = 0
    center = np.memmap(
        f, dtype='float32', mode='r', offset=offset, shape=(3), order='C')
    offset = 3 * 4
    sizes = np.memmap(
        f, dtype='float32', mode='r', offset=offset, shape=(3), order='C')
    offset += 3 * 4
    vmin, vmax = np.memmap(
        f, dtype='float32', mode='c', offset=offset, shape=(2), order='C')
    offset += 2 * 4
    nbins, = np.memmap(
        f, dtype='int32', mode='r', offset=offset, shape=1, order='C')
    offset += 4
    vbins_short = np.zeros(nbins)
    vbins_log = np.zeros(nbins)
    vbins_long = np.zeros(nbins * 2)
    vbins_short = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(nbins), order='C')
    offset += 8 * nbins
    vbins_long = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(2 * nbins), order='C')
    offset += 8 * nbins * 2
    vbins_log = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(nbins), order='C')
    offset += 8 * nbins
    fvel_para_perp = np.zeros((nbins, 2 * nbins))
    fvel_xy = np.zeros((2 * nbins, 2 * nbins))
    fvel_xz = np.zeros((2 * nbins, 2 * nbins))
    fvel_yz = np.zeros((2 * nbins, 2 * nbins))
    fvel_para_perp = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(nbins, 2 * nbins), order='C')
    offset += 8 * nbins * 2 * nbins
    fvel_xy = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(2 * nbins, 2 * nbins), order='C')
    offset += 8 * 2 * nbins * 2 * nbins
    fvel_xz = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(2 * nbins, 2 * nbins), order='C')
    offset += 8 * 2 * nbins * 2 * nbins
    print offset
    fvel_yz = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(2 * nbins, 2 * nbins), order='C')
    f.close()

    f = open(fpath + fname_1d, 'r')
    # skip headers
    offset = 9 * 4 + 8 * nbins * 4
    fvel_para = np.zeros(2 * nbins)
    fvel_perp = np.zeros(nbins)
    fvel_para_log = np.zeros(nbins)
    fvel_perp_log = np.zeros(nbins)
    fvel_para = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(2 * nbins), order='C')
    offset += 8 * nbins * 2
    fvel_perp = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(nbins), order='C')
    offset += 8 * nbins
    fvel_para_log = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(nbins), order='C')
    offset += 8 * nbins
    fvel_perp_log = np.memmap(
        f, dtype='float64', mode='c', offset=offset, shape=(nbins), order='C')
    f.close()

    # Adjust the vbins. For ions, the actual saved variables is
    # sqrt(m_i) * u
    smime = math.sqrt(pic_info.mime)
    if species == 'h':
        vbins_short /= smime
        vbins_long /= smime
        vmin /= smime
        vmax /= smime

    # Add small number to the distributions to avoid zeros
    # delta = vmin_2d * 0.1
    delta = 0.01
    fvel_para_perp += delta
    fvel_xy += delta
    fvel_xz += delta
    fvel_yz += delta

    # delta = vmin_1d * 0.1
    fvel_para += delta
    fvel_perp += delta
    vmin_2d = min(
        np.min(fvel_para_perp[np.nonzero(fvel_para_perp)]),
        np.min(fvel_xy[np.nonzero(fvel_xy)]),
        np.min(fvel_xz[np.nonzero(fvel_xz)]),
        np.min(fvel_yz[np.nonzero(fvel_yz)]))
    vmax_2d = max(
        np.max(fvel_para_perp[np.nonzero(fvel_para_perp)]),
        np.max(fvel_xy[np.nonzero(fvel_xy)]),
        np.max(fvel_xz[np.nonzero(fvel_xz)]),
        np.max(fvel_yz[np.nonzero(fvel_yz)]))
    vmin_1d = min(
        np.min(fvel_para[np.nonzero(fvel_para)]),
        np.min(fvel_perp[np.nonzero(fvel_perp)]))
    vmax_1d = max(
        np.max(fvel_para[np.nonzero(fvel_para)]),
        np.max(fvel_perp[np.nonzero(fvel_perp)]))

    fvelocity = collections.namedtuple("fvelocity", [
        'species', 'tframe', 'center', 'sizes', 'vmin', 'vmax', 'nbins',
        'vbins_short', 'vbins_long', 'vbins_log', 'fvel_para_perp', 'fvel_xy',
        'fvel_xz', 'fvel_yz', 'fvel_para', 'fvel_perp', 'fvel_para_log',
        'fvel_perp_log', 'vmin_2d', 'vmax_2d', 'vmin_1d', 'vmax_1d'
    ])

    fvel = fvelocity(
        species=species,
        tframe=tframe,
        center=center,
        sizes=sizes,
        vmin=vmin,
        vmax=vmax,
        nbins=nbins,
        vbins_short=vbins_short,
        vbins_long=vbins_long,
        vbins_log=vbins_log,
        fvel_para_perp=fvel_para_perp,
        fvel_xy=fvel_xy,
        fvel_xz=fvel_xz,
        fvel_yz=fvel_yz,
        fvel_para=fvel_para,
        fvel_perp=fvel_perp,
        fvel_para_log=fvel_para_log,
        fvel_perp_log=fvel_perp_log,
        vmin_2d=vmin_2d,
        vmax_2d=vmax_2d,
        vmin_1d=vmin_1d,
        vmax_1d=vmax_1d)
    return fvel


def read_energy_distribution(species,
                             tframe,
                             pic_info,
                             fname,
                             fpath='../spectrum/'):
    """Read particle energy spectrum from a file.

    Args:
        fpath: file path for the data.
        species: particle species.
        tframe: time frame.
        pic_info: particle information namedtuple.
    """
    ntot = pic_info.nx * pic_info.ny + pic_info.nz * pic_info.nppc
    elin, flin, elog, flog = get_energy_distribution(fpath + fname, ntot)
    fenergy = collections.namedtuple(
        'fenergy', ['species', 'elin', 'flin', 'elog', 'flog'])
    fene = fenergy(species=species, elin=elin, flin=flin, elog=elog, flog=flog)
    return fene


def plot_ptl_vdist(species, pic_info, base_directory):
    """Plot particle velocity distribution.
    """
    ct = 14
    fname_1d = 'vdist_1d-' + species + '.' + str(ct)
    fname_2d = 'vdist_2d-' + species + '.' + str(ct)
    fpath = base_directory + 'pic_analysis/' + 'vdistributions/'
    fvel1 = read_velocity_distribution('e', 14, pic_info, fname_1d, fname_2d,
                                       fpath)
    vbins_long = fvel1.vbins_long
    fxy1 = fvel1.fvel_xy
    fxz1 = fvel1.fvel_xz
    fyz1 = fvel1.fvel_yz
    ct = 15
    fname_1d = 'vdist_1d-' + species + '.' + str(ct)
    fname_2d = 'vdist_2d-' + species + '.' + str(ct)
    fvel2 = read_velocity_distribution('e', 15, pic_info, fname_1d, fname_2d,
                                       fpath)
    fxy2 = fvel2.fvel_xy
    fxz2 = fvel2.fvel_xz
    fyz2 = fvel2.fvel_yz
    ct = 17
    fname_1d = 'vdist_1d-' + species + '.' + str(ct)
    fname_2d = 'vdist_2d-' + species + '.' + str(ct)
    fvel3 = read_velocity_distribution('e', 17, pic_info, fname_1d, fname_2d,
                                       fpath)
    fxy3 = fvel3.fvel_xy
    fxz3 = fvel3.fvel_xz
    fyz3 = fvel3.fvel_yz
    nbins = fvel1.nbins * 2
    ns = nbins / 10
    ne = nbins * 9 / 10
    width = 0.2
    height = 0.25
    xs = xs0 = 0.1
    ys = 0.98 - height
    gap = 0.1
    gapv = 0.07
    fig = plt.figure(figsize=[10, 8])
    cmap = plt.cm.jet
    extent = [-0.8, 0.8, -0.8, 0.8]
    ax11 = fig.add_axes([xs, ys, width, height])
    pvxy1 = ax11.imshow(
        fxy1[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax11.tick_params(labelsize=16)
    ax11.set_xlabel(r'$u_x$', fontsize=20)
    ax11.set_ylabel(r'$u_y$', fontsize=20)
    ax11.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax11.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs1 = xs + 3 * width + 2 * gap + 0.02
    ys1 = ys - 2 * height - 2 * gapv
    h1 = 3 * height + 2 * gapv
    cax = fig.add_axes([xs1, ys1, 0.02, h1])
    cbar = fig.colorbar(pvxy1, cax=cax)
    cbar.ax.tick_params(labelsize=16)

    xs += width + gap
    ax12 = fig.add_axes([xs, ys, width, height])
    pvxz1 = ax12.imshow(
        fxz1[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax12.tick_params(labelsize=16)
    ax12.set_xlabel(r'$u_x$', fontsize=20)
    ax12.set_ylabel(r'$u_z$', fontsize=20)
    ax12.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax12.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs += width + gap
    ax13 = fig.add_axes([xs, ys, width, height])
    pvyz1 = ax13.imshow(
        fyz1[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax13.tick_params(labelsize=16)
    ax13.set_xlabel(r'$u_y$', fontsize=20)
    ax13.set_ylabel(r'$u_z$', fontsize=20)
    ax13.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax13.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs = xs0
    ys -= height + gapv
    ax21 = fig.add_axes([xs, ys, width, height])
    pvxy2 = ax21.imshow(
        fxy2[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax21.tick_params(labelsize=16)
    ax21.set_xlabel(r'$u_x$', fontsize=20)
    ax21.set_ylabel(r'$u_y$', fontsize=20)
    ax21.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax21.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs += width + gap
    ax22 = fig.add_axes([xs, ys, width, height])
    pvxz2 = ax22.imshow(
        fxz2[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax22.tick_params(labelsize=16)
    ax22.set_xlabel(r'$u_x$', fontsize=20)
    ax22.set_ylabel(r'$u_z$', fontsize=20)
    ax22.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax22.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs += width + gap
    ax23 = fig.add_axes([xs, ys, width, height])
    pvyz2 = ax23.imshow(
        fyz2[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax23.tick_params(labelsize=16)
    ax23.set_xlabel(r'$u_y$', fontsize=20)
    ax23.set_ylabel(r'$u_z$', fontsize=20)
    ax23.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax23.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs = xs0
    ys -= height + gapv
    ax31 = fig.add_axes([xs, ys, width, height])
    pvxy3 = ax31.imshow(
        fxy3[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax31.tick_params(labelsize=16)
    ax31.set_xlabel(r'$u_x$', fontsize=20)
    ax31.set_ylabel(r'$u_y$', fontsize=20)
    ax31.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax31.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs += width + gap
    ax32 = fig.add_axes([xs, ys, width, height])
    pvxz3 = ax32.imshow(
        fxz3[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax32.tick_params(labelsize=16)
    ax32.set_xlabel(r'$u_x$', fontsize=20)
    ax32.set_ylabel(r'$u_z$', fontsize=20)
    ax32.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax32.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    xs += width + gap
    ax33 = fig.add_axes([xs, ys, width, height])
    pvyz3 = ax33.imshow(
        fyz3[ns:ne, ns:ne],
        cmap=cmap,
        extent=extent,
        aspect='auto',
        origin='lower',
        norm=LogNorm(
            vmin=fvel1.vmin_2d, vmax=fvel1.vmax_2d),
        interpolation='bicubic')
    ax33.tick_params(labelsize=16)
    ax33.set_xlabel(r'$u_y$', fontsize=20)
    ax33.set_ylabel(r'$u_z$', fontsize=20)
    ax33.xaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))
    ax33.yaxis.set_ticks(np.arange(-0.8, 0.9, 0.4))

    # fig.savefig('../img/vdist.eps')

    plt.show()


def traj_sigma1():
    """
    """
    # base_directory = '../../'
    base_directory = '/net/scratch2/guofan/sigma1-mime25-beta001/'
    pic_info = pic_information.get_pic_info(base_directory)
    ntp = pic_info.ntp
    vthe = pic_info.vthe
    particle_interval = pic_info.particle_interval
    pos = [pic_info.lx_di / 10, 0.0, 2.0]
    corners, mpi_ranks = set_mpi_ranks(pic_info, pos)
    ct = 5 * particle_interval
    get_particle_distribution(base_directory, pic_info, ct, corners, mpi_ranks)
    smime = math.sqrt(pic_info.mime)
    lx_de = pic_info.lx_di * smime
    center = [0.5 * lx_de, 0, 0]
    sizes = [256, 1, 256]
    kwargs = {
        'center': center,
        'sizes': sizes,
        'nbins': 64,
        'vmax': 2.0,
        'vmin': 0,
        'tframe': 10,
        'species': 'e'
    }
    # get_spectrum_vdist(pic_info, **kwargs)
    species = 'e'
    ct = 10
    fpath = base_directory + 'pic_analysis/' + 'vdistributions/'
    fname_1d = 'vdist_1d-' + species + '.' + str(ct)
    fname_2d = 'vdist_2d-' + species + '.' + str(ct)
    fvel = read_velocity_distribution('e', ct, pic_info, fname_1d, fname_2d,
                                      fpath)
    fpath = base_directory + 'pic_analysis/' + 'spectrum/'
    fname_ene = 'spectrum-' + species + '.' + str(ct)
    fene = read_energy_distribution('e', ct, pic_info, fname_ene, fpath)
    plot_ptl_vdist('e', pic_info, base_directory)


def plot_particle_phase_distribution(pic_info, ct, base_dir, run_name, species,
                                     shock_pos):
    """
    """
    particle_interval = pic_info.particle_interval
    tratio = particle_interval / pic_info.fields_interval
    ptl_tindex = ct * particle_interval / tratio
    xmin, xmax = 0, pic_info.lx_di
    xmin, xmax = 0, 105
    zmin, zmax = -0.5 * pic_info.lz_di, 0.5 * pic_info.lz_di
    kwargs = {
        "current_time": ct,
        "xl": xmin,
        "xr": xmax,
        "zb": zmin,
        "zt": zmax
    }
    fname = base_dir + 'data1/vex.gda'
    x, z, vel = read_2d_fields(pic_info, fname, **kwargs)
    # nx, = x.shape
    # nz, = z.shape
    # data_cum = np.sum(vel, axis=0) / nz
    # data_grad = np.abs(np.gradient(data_cum))
    # xs = 5
    # max_index = np.argmax(data_grad[xs:])
    # xm = x[max_index]
    xm = x[shock_pos]
    max_index = shock_pos

    pos = [xm / 2, 0.0, 0.0]
    nxc = max_index
    csizes = [max_index, pic_info.ny, pic_info.nz]
    # csizes = [max_index/4, pic_info.ny, pic_info.nz/4]
    corners, mpi_ranks = set_mpi_ranks(pic_info, pos, sizes=csizes)

    fig1, fig2 = get_phase_distribution(base_dir, pic_info, species,
                                        ptl_tindex, corners, mpi_ranks)

    fig_dir = '../img/img_phase_distribution/' + run_name + '/'
    mkdir_p(fig_dir)
    fname = fig_dir + '/vdist_para_perp_' + species + '_' + str(ct).zfill(
        3) + '.jpg'
    fig1.savefig(fname, dpi=300)

    fname = fig_dir + '/vdist_para_perp_1d_' + species + '_' + str(ct).zfill(
        3) + '.jpg'
    fig2.savefig(fname, dpi=300)

    # plt.show()
    plt.close("all")


def get_particle_spectrum_rank(base_dir, pic_info, species, ct, ix):
    """Get particle spectrum for different mpi_rank

    Args:
        base_dir: the base directory for the simulation data.
        pic_info: PIC simulation information
        species: particle species
        ct: hydro fields time frame index
        ix: x index of mpi_rank
    """
    particle_interval = pic_info.particle_interval
    tratio = particle_interval / pic_info.fields_interval
    tindex = ct * particle_interval / tratio
    dir_name = base_dir + 'particles/T.' + str(tindex) + '/'
    fbase = dir_name + species + '.' + str(tindex) + '.'
    tx = pic_info.topology_x
    ty = pic_info.topology_y
    tz = pic_info.topology_z
    nbins = 601
    emin, emax = 1E-4, 1E2
    emin_log, emax_log = math.log10(emin), math.log10(emax)
    espectrum = np.zeros(nbins - 1)
    ene_bins = 10**np.linspace(emin_log, emax_log, nbins)
    if species == 'electron':
        ptl_mass = 1
    else:
        ptl_mass = pic_info.mime
    for iy in range(ty):
        for iz in range(tz):
            mpi_rank = ix + iy * tx + iz * tx * ty
            fname = fbase + str(mpi_rank)
            (v0, pheader, ptl) = read_particle_data(fname)
            gama = np.sqrt(np.sum(ptl['u']**2, axis=1) + 1)
            hist, ebins_edge = np.histogram(
                (gama - 1) * ptl_mass, bins=ene_bins)
            espectrum += hist

    ene_interval = np.diff(ene_bins)
    print 'number of particles:', np.sum(espectrum)
    espectrum /= ene_interval
    spect_data = np.vstack((ene_bins[:-1], espectrum))
    fname = dir_name + species + '_spect.' + str(tindex) + '.' + str(ix)
    spect_data.tofile(fname)

    # plt.loglog(ene_bins[:-1], espectrum/ene_interval)
    # plt.show()


def plot_particle_spectrum_rank(base_dir, pic_info, species, ct, xshock):
    """Plot particle spectrum for different mpi_rank

    Args:
        base_dir: the base directory for the simulation data.
        pic_info: PIC simulation information
        species: particle species
        ct: hydro fields time frame index
        xshock: x position of the shock
    """
    particle_interval = pic_info.particle_interval
    tratio = particle_interval / pic_info.fields_interval
    tindex = ct * particle_interval / tratio
    dir_name = base_dir + 'particles/T.' + str(tindex) + '/'
    fbase = dir_name + species + '.' + str(tindex) + '.'
    tx = pic_info.topology_x
    lx = pic_info.lx_di
    dx_mpi = lx / tx

    # Decide the maximum ix to plot using the shock location
    ix_max = int((xshock) / dx_mpi)  # shift 10 di

    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    fig = plt.figure(figsize=(7, 5))
    ax1 = fig.add_axes([xs, ys, w1, h1])
    fname_pre = dir_name + species + '_spect.' + str(tindex)
    fname = fname_pre + '.0'
    spect_data = np.fromfile(fname)
    sz, = spect_data.shape
    nbins = sz / 2
    espectrum_tot = np.zeros(nbins)
    cmap = plt.cm.jet
    print 'shock position ', ix_max
    for ix in range(ix_max):
        print ix
        fname = fname_pre + '.' + str(ix)
        spect_data = np.fromfile(fname)
        espectrum_tot += spect_data[nbins:]
        ax1.loglog(
            spect_data[:sz / 2],
            spect_data[sz / 2:],
            color=cmap(1 - ix / float(ix_max), 1),
            linewidth=3)

    # ax1.loglog(spect_data[:nbins], espectrum_tot)
    ax1.set_xlim([1E-3, 30])
    ax1.tick_params(labelsize=16)
    ax1.set_xlabel(r'$\varepsilon$', fontsize=20)
    ax1.set_ylabel(r'$dN/d\varepsilon$', fontsize=20)
    plt.show()


def plot_vdist_time(species, pic_info, run_name, nt):
    """Plot particle velocity distribution.
    """
    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])

    for ct in range(1, nt+1):
        fname_1d = 'vdist_1d-' + species + '.' + str(ct)
        fname_2d = 'vdist_2d-' + species + '.' + str(ct)
        fpath = '../vdistributions/' + run_name + '/'
        fvel1 = read_velocity_distribution(species, ct, pic_info, fname_1d,
                                           fname_2d, fpath)
        vbins_short = fvel1.vbins_short
        vbins_long = fvel1.vbins_long
        vbins_log = fvel1.vbins_log
        fvel_para = fvel1.fvel_para
        fvel_perp = fvel1.fvel_perp
        fvel_para_log = fvel1.fvel_para_log
        fvel_perp_log = fvel1.fvel_perp_log
        dvbins_log = np.gradient(vbins_log)

        print np.sum(fvel_para_log), np.sum(fvel_perp_log)

        fvel_para_log /= dvbins_log
        fvel_perp_log /= dvbins_log
        # fvel_perp_log *= 0.5

        # fig = plt.figure(figsize=[7, 5])
        # xs, ys = 0.15, 0.15
        # w1, h1 = 0.8, 0.8
        # ax = fig.add_axes([xs, ys, w1, h1])

        # ax.loglog(vbins_log, fvel_para_log, linewidth=2,
        #         color='r', label='Para')
        # ax.loglog(vbins_log, fvel_perp_log, linewidth=2,
        #         color='b', label='Perp')
        color = plt.cm.jet(ct / float(nt), 1)
        ax.loglog(vbins_log, fvel_para_log/fvel_perp_log,
                linewidth=2, color=color, label=str(ct))

    ax.tick_params(labelsize=16)
    # ax.set_xlabel(r'$p_\parallel, p_\perp$', fontdict=font, fontsize=20)
    # ax.set_ylabel(r'$f(p_\parallel), f(p_\perp)$', fontdict=font, fontsize=20)
    # leg = ax.legend(loc=3, prop={'size': 20}, ncol=1,
    #     shadow=False, fancybox=False, frameon=False)
    ax.loglog(ax.get_xlim(), [1, 1], color='k', linestyle='--')
    ax.loglog(ax.get_xlim(), [0.1, 0.1], color='k', linestyle='--')
    ax.loglog(ax.get_xlim(), [10, 10], color='k', linestyle='--')
    ax.set_xlabel(r'$p_\parallel, p_\perp$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$f(p_\parallel)/f(p_\perp)$', fontdict=font, fontsize=20)
    ax.set_xlim([1E-2, 2E1])

    plt.show()


def shock_current_sheet():
    """
    """
    ct = 370
    cts = range(10, pic_info.ntf - 1, tratio)
    ixs = range(pic_info.topology_x)
    shock_loc = np.genfromtxt(
        '../data/shock_pos/shock_pos.txt', dtype=np.int32)
    xmin, xmax = 0, 105
    zmin, zmax = -0.5 * pic_info.lz_di, 0.5 * pic_info.lz_di
    kwargs = {
        "current_time": ct,
        "xl": xmin,
        "xr": xmax,
        "zb": zmin,
        "zt": zmax
    }
    fname = base_dir + 'data1/vex.gda'
    x, z, vx = read_2d_fields(pic_info, fname, **kwargs)
    xm = x[shock_loc[ct]]


if __name__ == "__main__":
    cmdargs = sys.argv
    if (len(cmdargs) > 2):
        base_dir = cmdargs[1]
        run_name = cmdargs[2]
    else:
        base_dir = '/net/scratch3/xiaocanli/2D-90-Mach4-sheet4-multi/'
        run_name = '2D-90-Mach4-sheet4-multi'
    picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    tratio = pic_info.particle_interval / pic_info.fields_interval

    nt = pic_info.ntp
    plot_vdist_time('e', pic_info, run_name, nt)

    # shock_current_sheet()

    def processInput(job_id):
        print job_id
        ct = job_id
        plot_particle_phase_distribution(pic_info, ct, base_dir, run_name,
                                         'electron', shock_loc[ct])
        plot_particle_phase_distribution(pic_info, ct, base_dir, run_name,
                                         'ion', shock_loc[ct])
        # get_particle_spectrum_rank(base_dir, pic_info, 'ion', ct, job_id)

    num_cores = multiprocessing.cpu_count()
    # Parallel(n_jobs=num_cores)(delayed(processInput)(ct) for ct in cts)
    # plot_particle_phase_distribution(pic_info, ct, base_dir,
    #         run_name, 'ion', shock_loc[ct])
    # Parallel(n_jobs=num_cores)(delayed(processInput)(ix) for ix in ixs)
    # get_particle_spectrum_rank(base_dir, pic_info, 'electron', ct, 0)
    # plot_particle_spectrum_rank(base_dir, pic_info, 'ion', ct, xm)
