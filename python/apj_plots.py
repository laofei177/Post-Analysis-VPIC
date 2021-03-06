"""
Functions and classes for 2D contour plots of fields.
"""
import collections
import math
import os
import os.path
import pprint
import re
import stat
import struct
import sys
import itertools
from itertools import groupby
from os import listdir
from os.path import isfile, join

import functools
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from cycler import cycler
from joblib import Parallel, delayed
from matplotlib import rc
from matplotlib.colors import LogNorm
from matplotlib.ticker import MaxNLocator
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.mplot3d import Axes3D
from scipy import signal
from scipy import optimize
from scipy.fftpack import fft2, fftshift, ifft2
from scipy.interpolate import interp1d, RectBivariateSpline
from scipy.ndimage.filters import generic_filter as gf

import color_maps as cm
import colormap.colormaps as cmaps
import palettable
import pic_information
from contour_plots import plot_2d_contour, read_2d_fields
from distinguishable_colors import *
from energy_conversion import calc_jdotes_fraction_multi, read_data_from_json
from energy_conversion import plot_energy_evolution
from fields_plot import *
from particle_distribution import *
from pic_information import list_pic_info_dir
from runs_name_path import ApJ_long_paper_runs
from shell_functions import mkdir_p
from spectrum_fitting import *

rc('font', **{'family': 'serif', 'serif': ['Computer Modern']})
mpl.rc('text', usetex=True)
mpl.rcParams['text.latex.preamble'] = [r"\usepackage{amsmath}"]

font = {
    'family': 'serif',
    # 'color':'darkred',
    'color': 'black',
    'weight': 'normal',
    'size': 24,
}

colors = palettable.colorbrewer.qualitative.Set1_9.mpl_colors

# colors = palettable.colorbrewer.qualitative.Dark2_8.mpl_colors

def zfunc(y, x):
    """Function to adjust the agyrotropy calculated using simulation data
    """
    return (x + math.exp(-x**2)/(math.sqrt(math.pi) * (1.0 + math.erf(x))) - y)


def calc_agyrotropy(run_name, root_dir, pic_info, species, current_time):
    """Calculate pressure agyrotropy

    Args:
        run_name: run name
        root_dir: the root directory of the run
        pic_info: namedtuple for the PIC simulation information.
        current_time: current time frame.
    """
    print(current_time)
    kwargs = {
        "current_time": current_time,
        "xl": 0,
        "xr": 200,
        "zb": -20,
        "zt": 20
    }
    fname = root_dir + 'data/p' + species + '-xx.gda'
    x, z, pxx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/p' + species + '-xy.gda'
    x, z, pxy = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/p' + species + '-xz.gda'
    x, z, pxz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/p' + species + '-yy.gda'
    x, z, pyy = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/p' + species + '-yz.gda'
    x, z, pyz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/p' + species + '-zz.gda'
    x, z, pzz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/absB.gda'
    x, z, absB = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/n' + species + '.gda'
    x, z, nrho = read_2d_fields(pic_info, fname, **kwargs)
    nrho *= pic_info.nppc  # Assume n0 is 1.0
    bx /= absB
    by /= absB
    bz /= absB
    nx, = x.shape
    nz, = z.shape
    zmin = np.min(z)
    zmax = np.max(z)

    ng = 7
    kernel = np.ones((ng,ng)) / float(ng*ng)
    pxx = signal.convolve2d(pxx, kernel, mode='same')
    pxy = signal.convolve2d(pxy, kernel, mode='same')
    pxz = signal.convolve2d(pxz, kernel, mode='same')
    pyy = signal.convolve2d(pyy, kernel, mode='same')
    pyz = signal.convolve2d(pyz, kernel, mode='same')
    pzz = signal.convolve2d(pzz, kernel, mode='same')
    bx = signal.convolve2d(bx, kernel, mode='same')
    by = signal.convolve2d(by, kernel, mode='same')
    bz = signal.convolve2d(bz, kernel, mode='same')

    Nxx =  by*by*pzz - 2.0*by*bz*pyz + bz*bz*pyy
    Nxy = -by*bx*pzz + by*bz*pxz + bz*bx*pyz - bz*bz*pxy
    Nxz =  by*bx*pyz - by*by*pxz - bz*bx*pyy + bz*by*pxy
    Nyy =  bx*bx*pzz - 2.0*bx*bz*pxz + bz*bz*pxx
    Nyz = -bx*bx*pyz + bx*by*pxz + bz*bx*pxy - bz*by*pxx
    Nzz =  bx*bx*pyy - 2.0*bx*by*pxy + by*by*pxx

    alpha = Nxx + Nyy + Nzz
    beta = -(Nxy**2 + Nxz**2 + Nyz**2 - Nxx*Nyy - Nxx*Nzz - Nyy*Nzz)
    agyrotropy = 2.0 * np.sqrt(alpha**2-4.0*beta)/alpha

    sqrt_pi = math.sqrt(math.pi)
    isqrt_pi = 1.0 / sqrt_pi
    # Adjust the calculated values
    sigma_n = 2.5 *  sqrt_pi / np.sqrt(nrho)

    agyrotropy_p = np.zeros((nz, nx))
            
    # for iz in range(nz):
    #     for ix in range(nx):
    #         y = agyrotropy[iz, ix]/sigma_n[iz, ix]
    #         if isqrt_pi < y:
    #             f = functools.partial(zfunc, y)
    #             agyrotropy_p[iz, ix] = optimize.brenth(f, 0, 5)

    # agyrotropy = agyrotropy_p * sigma_n

    return agyrotropy


def plot_agyrotropy(run_name, root_dir, pic_info, species, current_time):
    """Plot agyrotropy

    Args:
        run_name: run name
        root_dir: the root directory of the run
        pic_info: namedtuple for the PIC simulation information.
        current_time: current time frame.
    """
    print(current_time)
    kwargs = {
        "current_time": current_time,
        "xl": 0,
        "xr": 200,
        "zb": -20,
        "zt": 20
    }
    # fname = root_dir + 'data1/agyrotropy00_' + species + '.gda'
    # x, z, fdata = read_2d_fields(pic_info, fname, **kwargs)
    fdata = calc_agyrotropy(run_name, root_dir, pic_info, species, current_time)
    x, z, Ay = read_2d_fields(pic_info, root_dir + "data/Ay.gda", **kwargs)
    nx, = x.shape
    nz, = z.shape
    zmin = np.min(z)
    zmax = np.max(z)

    # ng = 7
    # kernel = np.ones((ng,ng)) / float(ng*ng)
    # fdata = signal.convolve2d(fdata, kernel, mode='same')
    
    xs, ys = 0.12, 0.15
    w1, h1 = 0.8, 0.8
    fig = plt.figure(figsize=[10, 4])
    ax1 = fig.add_axes([xs, ys, w1, h1])
    kwargs_plot = {"xstep": 1, "zstep": 1, "vmin": 0.0, "vmax": 1.0}
    xstep = kwargs_plot["xstep"]
    zstep = kwargs_plot["zstep"]
    p1, cbar1 = plot_2d_contour(x, z, fdata, ax1, fig, **kwargs_plot)
    p1.set_cmap(plt.cm.get_cmap('viridis'))
    ax1.contour(x[0:nx:xstep], z[0:nz:zstep], Ay[0:nz:zstep, 0:nx:xstep],
        colors='black', linewidths=0.5)
    # ax1.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
    ax1.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)
    cbar1.ax.set_ylabel(r'$A\O_e$', fontdict=font, fontsize=20)
    cbar1.set_ticks(np.arange(0.0, 1.1, 0.5))
    cbar1.ax.tick_params(labelsize=16)

    x0s = np.linspace(150, 180, 4)
    # x0s = np.linspace(80, 50, 4)
    # x0s = np.linspace(50, 80, 4)
    for x0 in x0s:
        dx = pic_info.dx_di
        ix = int(x0 / dx)
        ax1.plot([x0, x0], [zmin, zmax], linestyle='--')

    t_wci = current_time * pic_info.dt_fields
    title = r'$t = ' + "{:10.1f}".format(t_wci) + '/\Omega_{ci}$'
    ax1.set_title(title, fontdict=font, fontsize=20)

    ipath = '../img/img_apj/revise/'
    mkdir_p(ipath)
    fname = ipath + 'agy2.jpg'
    fig.savefig(fname)

    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])

    for x0 in x0s:
        dx = pic_info.dx_di
        ix = int(x0 / dx)
        fdata_cut = fdata[:, ix]
        # print np.min(fdata_cut), np.max(fdata_cut)
        ax.plot(z, fdata_cut, linewidth=2)
    
    min_index = np.argmin(fdata_cut)
    ax.set_xlim([-10, 10])
    ax.set_ylim([-0.1, 1.0])
    ax.tick_params(labelsize=16)
    ax.set_xlabel(r'$z/d_i$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$A\O_e$', fontdict=font, fontsize=20)

    fname = ipath + 'agy_cut2.eps'
    fig.savefig(fname)

    plt.show()
    # plt.close()


def plot_absB(run_name, root_dir, pic_info, current_time):
    """Plot absB

    Args:
        run_name: run name
        root_dir: the root directory of the run
        pic_info: namedtuple for the PIC simulation information.
        current_time: current time frame.
    """
    print(current_time)
    kwargs = {
        "current_time": current_time,
        "xl": 0,
        "xr": 200,
        "zb": -20,
        "zt": 20
    }
    x, z, absB = read_2d_fields(pic_info, root_dir + 'data/absB.gda', **kwargs)
    x, z, Ay = read_2d_fields(pic_info, root_dir + "data/Ay.gda", **kwargs)
    nx, = x.shape
    nz, = z.shape
    zmin = np.min(z)
    zmax = np.max(z)
    width = 0.63
    height = 0.7
    xs = 0.31
    ys = 0.9 - height
    fig = plt.figure(figsize=[13, 4])
    ax1 = fig.add_axes([xs, ys, width, height])
    kwargs_plot = {"xstep": 1, "zstep": 1, "vmin": 0.0, "vmax": 2.0}
    xstep = kwargs_plot["xstep"]
    zstep = kwargs_plot["zstep"]
    p1, cbar1 = plot_2d_contour(x, z, absB, ax1, fig, **kwargs_plot)
    p1.set_cmap(plt.cm.get_cmap('jet'))
    ax1.contour(
        x[0:nx:xstep],
        z[0:nz:zstep],
        Ay[0:nz:zstep, 0:nx:xstep],
        colors='black',
        linewidths=0.5)
    ax1.set_ylabel('', fontdict=font, fontsize=20)
    ax1.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)
    cbar1.ax.set_ylabel(r'$|\boldsymbol{B}|$', fontdict=font, fontsize=20)
    cbar1.set_ticks(np.arange(0.0, 2.1, 0.5))
    cbar1.ax.tick_params(labelsize=16)
    ax1.tick_params(axis='y', labelleft='off')

    x0 = 150.0
    dx = pic_info.dx_di
    ix = x0 / dx

    w2 = 0.22
    xs -= w2 + 0.02
    ax = fig.add_axes([xs, ys, w2, height])
    for x0 in np.linspace(150, 180, 4):
        dx = pic_info.dx_di
        ix = int(x0 / dx)
        ax1.plot([x0, x0], [zmin, zmax], linestyle='--')
        ax.plot(absB[:, ix], z, linewidth=2)
    ax.set_ylim([np.min(z), np.max(z)])
    ax.tick_params(labelsize=16)
    ax.set_xlabel(r'$|\boldsymbol{B}|$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)

    t_wci = current_time * pic_info.dt_fields
    title = r'$t = ' + "{:10.1f}".format(t_wci) + '/\Omega_{ci}$'
    ax1.set_title(title, fontdict=font, fontsize=20)

    ipath = '../img/img_apj/revise/'
    mkdir_p(ipath)
    fname = ipath + 'absB.jpg'
    fig.savefig(fname)

    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    x0 = 160
    dx = pic_info.dx_di
    ix = int(x0 / dx)
    fdata = absB[:, ix]
    print np.min(fdata), np.max(fdata)
    ax.plot(z, fdata, linewidth=2, color='g')
    ax.plot([zmin, zmax], [0.5, 0.5], linestyle='--', color='k')
    ax.set_ylim([0.1, 1.0])

    min_index = np.argmin(fdata)
    # for iz in range(min_index - 15, min_index + 15):
    #     print iz, fdata[iz]
    
    iz1, iz2 = 399, 420
    ax.plot([z[iz1], z[iz1]], ax.get_ylim(), linestyle='-', color='k')
    ax.plot([z[iz2], z[iz2]], ax.get_ylim(), linestyle='-', color='k')
    ax.set_xlim([zmin, zmax])
    ax.tick_params(labelsize=16)
    ax.set_xlabel(r'$z/d_i$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$|\boldsymbol{B}|$', fontdict=font, fontsize=20)

    fname = ipath + 'absB_cut.jpg'
    fig.savefig(fname)

    plt.show()
    # plt.close()


def plot_absB_time(run_name, root_dir, pic_info):
    """Plot absB contour at multiple time frames

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
    """
    ct = 80
    nt = 3
    contour_color = ['k'] * nt
    vmin = [0.0] * nt
    vmax = [1.2] * nt
    xs, ys = 0.18, 0.76
    w1, h1 = 0.68, 0.2
    fig_sizes = (5, 6)
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.02]
    nxp, nzp = 1, nt
    cts = [60, 152.5, 800]
    cts = np.asarray(cts)
    var_names = []
    for i in range(nt):
        var_name = r'$t=' + str(cts[i]) + r'/\Omega_{ci}$'
        var_names.append(var_name)
    cts /= pic_info.dt_fields
    cts = np.asarray(cts - 1, dtype=int)
    print cts
    colormaps = ['viridis'] * nt
    text_colors = ['r', 'g', 'b']
    xstep, zstep = 2, 2
    is_logs = [False] * nt
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_apj/'
    if not os.path.isdir(dir):
        os.makedirs(dir)
    fig_dir = dir + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    fname1 = root_dir + 'data/absB.gda'
    fname2 = root_dir + 'data/Ay.gda'
    fdata = []
    Ay_data = []
    fdata_1d = []
    for i in range(nt):
        kwargs["current_time"] = cts[i]
        x, z, data = read_2d_fields(pic_info, fname1, **kwargs)
        x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
        nz, = z.shape
        fdata.append(data)
        Ay_data.append(Ay)
        fdata_1d.append(data[nz/2, :])

    fdata = np.asarray(fdata)
    fdata_1d = np.asarray(fdata_1d)

    fname = 'absB_time'
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay_data,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'is_multi_Ay': True,
        'save_eps': True,
        'bottom_panel': True,
        'fdata_1d': fdata_1d
    }
    absB_plot = PlotMultiplePanels(**kwargs_plots)
    for cbar in absB_plot.cbar:
        cbar.set_ticks(np.arange(0.0, 1.3, 0.2))
    xbox = [104, 134, 134, 104, 104]
    zbox = [-15, -15, 15, 15, -15]
    absB_plot.ax[1].plot(xbox, zbox, color='k')
    absB_plot.save_figures()
    plt.show()


def plot_by_time(run_name, root_dir, pic_info):
    """Plot by contour at multiple time frames

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
    """
    ct = 80
    nt = 3
    contour_color = ['k'] * nt
    vmin = [-1.0] * nt
    vmax = [1.0] * nt
    xs, ys = 0.18, 0.7
    w1, h1 = 0.68, 0.28
    fig_sizes = (5, 6)
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.02]
    nxp, nzp = 1, nt
    cts = [60, 152.5, 800]
    cts = np.asarray(cts)
    var_names = []
    for i in range(nt):
        var_name = r'$t=' + str(cts[i]) + r'/\Omega_{ci}$'
        var_names.append(var_name)
    cts /= pic_info.dt_fields
    cts = np.asarray(cts - 1, dtype=int)
    colormaps = ['seismic'] * nt
    text_colors = ['k'] * nt
    xstep, zstep = 2, 2
    is_logs = [False] * nt
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_apj/'
    if not os.path.isdir(dir):
        os.makedirs(dir)
    fig_dir = dir + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    fname1 = root_dir + 'data/by.gda'
    fname2 = root_dir + 'data/Ay.gda'
    fdata = []
    Ay_data = []
    for i in range(nt):
        kwargs["current_time"] = cts[i]
        x, z, data = read_2d_fields(pic_info, fname1, **kwargs)
        x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
        fdata.append(data)
        Ay_data.append(Ay)
    fname = 'by_time'
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay_data,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'is_multi_Ay': True,
        'save_eps': True
    }
    by_plot = PlotMultiplePanels(**kwargs_plots)
    for cbar in by_plot.cbar:
        cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    xbox = [104, 134, 134, 104, 104]
    zbox = [-15, -15, 15, 15, -15]
    by_plot.ax[1].plot(xbox, zbox, color='k')
    by_plot.save_figures()
    plt.show()


def plot_vx_time(run_name, root_dir, pic_info):
    """Plot jdote due to different drift current

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
    """
    ct = 0
    nt = 2
    contour_color = ['k'] * nt
    vmin = [-1.0] * nt
    vmax = [1.0] * nt
    xs, ys = 0.18, 0.7
    w1, h1 = 0.68, 0.28
    fig_sizes = (5, 6)
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.02]
    nxp, nzp = 1, nt
    cts = [60, 152.5]
    cts = np.asarray(cts)
    var_names = []
    for i in range(nt):
        var_name = r'$t=' + str(cts[i]) + r'/\Omega_{ci}$'
        var_names.append(var_name)
    cts /= pic_info.dt_fields
    cts = np.asarray(cts - 1, dtype=int)
    colormaps = ['seismic'] * nt
    text_colors = [colors[0], colors[1]]
    xstep, zstep = 2, 2
    is_logs = [False] * nt
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_apj/'
    if not os.path.isdir(dir):
        os.makedirs(dir)
    fig_dir = dir + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    fname11 = root_dir + 'data/vex.gda'
    if not os.path.isfile(fname11):
        fname11 = root_dir + 'data/uex.gda'
    fname12 = root_dir + 'data/ne.gda'
    fname21 = root_dir + 'data/vix.gda'
    if not os.path.isfile(fname21):
        fname21 = root_dir + 'data/uix.gda'
    fname22 = root_dir + 'data/ni.gda'
    fname3 = root_dir + 'data/Ay.gda'
    mime = pic_info.mime
    fdata = []
    fdata_1d = []
    Ay_data = []
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    for i in range(nt):
        kwargs["current_time"] = cts[i]
        x, z, vex = read_2d_fields(pic_info, fname11, **kwargs)
        x, z, ne = read_2d_fields(pic_info, fname12, **kwargs)
        x, z, vix = read_2d_fields(pic_info, fname21, **kwargs)
        x, z, ni = read_2d_fields(pic_info, fname22, **kwargs)
        ux = (ne * vex + ni * vix * mime) / (ne + ni * mime)
        ux /= va
        x, z, Ay = read_2d_fields(pic_info, fname3, **kwargs)
        nx, = x.shape
        nz, = z.shape
        fdata.append(ux)
        fdata_1d.append(ux[nz / 2, :])
        Ay_data.append(Ay)
    fname = 'vx_time'
    fdata = np.asarray(fdata)
    fdata_1d = np.asarray(fdata_1d)
    fname = 'vx_time'
    bottom_panel = True
    xlim = [0, 200]
    zlim = [-50, 50]
    save_eps = True
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay_data,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'bottom_panel': bottom_panel,
        'fdata_1d': fdata_1d,
        'xlim': xlim,
        'zlim': zlim,
        'is_multi_Ay': True,
        'save_eps': save_eps
    }
    vx_plot = PlotMultiplePanels(**kwargs_plots)
    for cbar in vx_plot.cbar:
        cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    vx_plot.ax1d.set_ylabel(r'$v_x/v_A$', fontdict=font, fontsize=20)
    xmin = np.min(x)
    xmax = np.max(x)
    zmin = np.min(z)
    zmax = np.max(z)
    z0 = z[nz / 2]
    vx_plot.ax[0].plot([xmin, xmax], [z0, z0], linestyle='--', color='k')
    vx_plot.ax[1].plot([xmin, xmax], [z0, z0], linestyle='--', color='k')
    # x0 = 127
    # vx_plot.ax[1].plot([x0, x0], [zmin, zmax], linestyle='--', color='k')
    xbox = [104, 134, 134, 104, 104]
    zbox = [-15, -15, 15, 15, -15]
    vx_plot.ax[1].plot(xbox, zbox, color='k')
    vx_plot.save_figures()
    plt.show()


def plot_epara_eperp(pic_info, ct, root_dir='../../'):
    # kwargs = {"current_time": ct, "xl": 50, "xr": 150, "zb": -10, "zt": 10}
    kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/absB.gda'
    x, z, absB = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ex.gda'
    x, z, ex = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ey.gda'
    x, z, ey = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ez.gda'
    x, z, ez = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)

    absE = np.sqrt(ex * ex + ey * ey + ez * ez)
    epara = (ex * bx + ey * by + ez * bz) / absB
    eperp = np.sqrt(absE * absE - epara * epara)
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    epara = signal.convolve2d(epara, kernel)
    eperp = signal.convolve2d(eperp, kernel)
    ey = signal.convolve2d(ey, kernel, 'same')

    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    e0 = va * b0
    epara /= 0.5 * e0
    ey /= 0.5 * e0

    contour_color = ['k'] * 2
    vmin = [-0.25, -1.0]
    vmax = [0.25, 1.0]
    xs, ys = 0.18, 0.58
    w1, h1 = 0.68, 0.38
    fig_sizes = (5, 4)
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.05]
    nxp, nzp = 1, 2
    var_names = [r'$E_\parallel$', r'$E_y$']
    colormaps = ['seismic', 'seismic']
    text_colors = ['k', 'k']
    xstep, zstep = 2, 2
    is_logs = [False] * 2
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_apj/'
    if not os.path.isdir(dir):
        os.makedirs(dir)
    fig_dir = dir + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)

    fdata = [epara, ey]
    Ay_data = Ay
    fname = 'epara_ey'
    fdata = np.asarray(fdata)
    # xlim = [50, 150]
    # zlim = [-10, 10]
    xlim = [0, 200]
    zlim = [-50, 50]
    save_eps = True
    nlevels_contour = 11
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay_data,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'xlim': xlim,
        'zlim': zlim,
        'is_multi_Ay': False,
        'save_eps': save_eps
    }
    vx_plot = PlotMultiplePanels(**kwargs_plots)
    # for cbar in vx_plot.cbar:
    #     cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    cbars = vx_plot.cbar
    cbars[0].set_ticks(np.arange(-0.2, 0.3, 0.1))
    cbars[1].set_ticks(np.arange(-0.8, 0.9, 0.4))
    vx_plot.save_figures()
    plt.show()

    # nx, = x.shape
    # nz, = z.shape
    # width = 0.73
    # height = 0.36
    # xs = 0.15
    # ys = 0.92 - height
    # gap = 0.05

    # fig = plt.figure(figsize=[7, 5])
    # ax1 = fig.add_axes([xs, ys, width, height])
    # kwargs_plot = {"xstep":2, "zstep":2, "vmin":-0.1, "vmax":0.1}
    # xstep = kwargs_plot["xstep"]
    # zstep = kwargs_plot["zstep"]
    # p1, cbar1 = plot_2d_contour(x, z, ey, ax1, fig, **kwargs_plot)
    # # p1.set_cmap(cmaps.inferno)
    # p1.set_cmap(plt.cm.get_cmap('seismic'))
    # Ay_min = np.min(Ay)
    # Ay_max = np.max(Ay)
    # levels = np.linspace(Ay_min, Ay_max, 10)
    # ax1.contour(x[0:nx:xstep], z[0:nz:zstep], Ay[0:nz:zstep, 0:nx:xstep],
    #         colors='k', linewidths=0.5)
    # ax1.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
    # # ax1.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=24)
    # ax1.tick_params(axis='x', labelbottom='off')
    # ax1.tick_params(labelsize=16)
    # # cbar1.ax.set_ylabel(r'$E_\perp$', fontdict=font, fontsize=20)
    # cbar1.set_ticks(np.arange(-0.08, 0.1, 0.04))
    # cbar1.ax.tick_params(labelsize=16)
    # ax1.text(0.02, 0.8, r'$E_y$', color='k', fontsize=20,
    #         bbox=dict(facecolor='none', alpha=1.0, edgecolor='none',
    #             pad=10.0), horizontalalignment='left',
    #         verticalalignment='center', transform = ax1.transAxes)

    # ys -= height + gap
    # ax2 = fig.add_axes([xs, ys, width, height])
    # kwargs_plot = {"xstep":1, "zstep":1, "vmin":-0.05, "vmax":0.05}
    # p2, cbar2 = plot_2d_contour(x, z, epara, ax2, fig, **kwargs_plot)
    # p2.set_cmap(plt.cm.seismic)
    # # p2.set_cmap(cmaps.plasma)
    # ax2.contour(x[0:nx:xstep], z[0:nz:zstep], Ay[0:nz:zstep, 0:nx:xstep],
    #         colors='black', linewidths=0.5)
    # ax2.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
    # ax2.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=20)
    # ax2.tick_params(labelsize=16)
    # # cbar2.ax.set_ylabel(r'$E_\parallel$', fontdict=font, fontsize=24)
    # cbar2.set_ticks(np.arange(-0.04, 0.05, 0.02))
    # cbar2.ax.tick_params(labelsize=16)
    # ax2.text(0.02, 0.8, r'$E_\parallel$', color='k', fontsize=20,
    #          bbox=dict(facecolor='none', alpha=1.0, edgecolor='none',
    #                    pad=10.0), horizontalalignment='left',
    #          verticalalignment='center', transform=ax2.transAxes)

    # # dtf = pic_info.dt_fields
    # dtf = 2.5
    # t_wci = (ct + 1) * dtf
    # title = r'$t = ' + "{:10.1f}".format(t_wci) + '/\Omega_{ci}$'
    # ax1.set_title(title, fontdict=font, fontsize=20)

    # if not os.path.isdir('../img/'):
    #     os.makedirs('../img/')
    # dir = '../img/img_apj/'
    # if not os.path.isdir(dir):
    #     os.makedirs(dir)
    # fname = dir + 'epara_perp' + '_' + str(ct).zfill(3) + '.eps'
    # fig.savefig(fname)

    plt.show()
    # plt.close()


def plot_jpara_dote(run_name, root_dir, pic_info, species):
    """Plot jdote due to different parallel current

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        species: particle species.
    """
    ct = 0
    nj = 1
    contour_color = ['k'] * nj
    vmin = [-1.0] * nj
    vmax = [1.0] * nj
    xs, ys = 0.11, 0.59
    w1, h1 = 0.8, 0.38
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.05]
    fig_sizes = (8, 4)
    nxp, nzp = 1, nj
    var_sym = ['\parallel']
    var_names = []
    for var in var_sym:
        var_name = r'$\boldsymbol{j}_' + var + r'\cdot\boldsymbol{E}$'
        var_names.append(var_name)
    colormaps = ['seismic'] * nj
    text_colors = colors[0:nj]
    xstep, zstep = 2, 2
    is_logs = [False] * nj
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    j0 = 0.1 * va**2 * b0
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jpara_dote/'
    if not os.path.isdir(dir):
        os.makedirs(dir)
    fig_dir = dir + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    fnames = []
    fname = root_dir + 'data1/jqnvpara_dote00_' + species + '.gda'
    fnames.append(fname)
    dv = pic_info.dx_di * pic_info.dz_di * pic_info.mime
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    fdata = []
    fdata_1d = []
    for fname in fnames:
        x, z, data = read_2d_fields(pic_info, fname, **kwargs)
        fdata_cum = np.cumsum(np.sum(data, axis=0)) * dv
        fdata_1d.append(fdata_cum)
        data_new = signal.convolve2d(data, kernel, 'same')
        fdata.append(data_new)
    fdata = np.asarray(fdata)
    fdata_1d = np.asarray(fdata_1d)
    fdata /= j0  # Normalization
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    fname = 'jpara_dote_' + species
    bottom_panel = True
    xlim = [0, 200]
    zlim = [-25, 25]
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'bottom_panel': bottom_panel,
        'fdata_1d': fdata_1d,
        'xlim': xlim,
        'zlim': zlim
    }
    jdote_plot = PlotMultiplePanels(**kwargs_plots)
    for ct in range(1, pic_info.ntf):
        kwargs["current_time"] = ct
        fdata = []
        fdata_1d = []
        for fname in fnames:
            x, z, data = read_2d_fields(pic_info, fname, **kwargs)
            fdata_cum = np.cumsum(np.sum(data, axis=0)) * dv
            fdata_1d.append(fdata_cum)
            data_new = signal.convolve2d(data, kernel, 'same')
            fdata.append(data_new)
        fdata = np.asarray(fdata)
        fdata_1d = np.asarray(fdata_1d)
        fdata /= j0  # Normalization
        x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
        jdote_plot.update_plot_1d(fdata_1d)
        jdote_plot.update_fields(ct, fdata, Ay)

    plt.close()
    # plt.show()


def plot_jdotes_fields(run_name, root_dir, pic_info, species, ct, srange,
                       axis_pos, gaps, fig_sizes):
    """Plot jdote due to different drift current

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        species: particle species.
        ct: current time frame
        srange: spatial range
    """
    nj = 5
    contour_color = ['k'] * nj
    vmin = [-1.0] * nj
    vmax = [1.0] * nj
    nxp, nzp = 1, nj
    var_sym = ['c', 'g', 'm', 'p', 'a', '\parallel', '\perp']
    var_names = []
    for var in var_sym:
        var_name = r'$\boldsymbol{j}_' + var + r'\cdot\boldsymbol{E}$'
        var_names.append(var_name)
    colormaps = ['seismic'] * nj
    text_colors = ['b', 'g', 'r', 'c', 'm']
    xstep, zstep = 1, 1
    is_logs = [False] * nj
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    j0 = 0.1 * va**2 * b0
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    if not os.path.isdir(dir):
        os.makedirs(dir)
    fig_dir = dir + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    fnames = []
    fname = root_dir + 'data1/jcpara_dote00_' + species + '.gda'
    fnames.append(fname)
    fname = root_dir + 'data1/jgrad_dote00_' + species + '.gda'
    fnames.append(fname)
    fname = root_dir + 'data1/jmag_dote00_' + species + '.gda'
    fnames.append(fname)
    fname = root_dir + 'data1/jpolar_dote00_' + species + '.gda'
    fnames.append(fname)
    fname = root_dir + 'data1/jagy_dote00_' + species + '.gda'
    fnames.append(fname)
    # fname = root_dir + 'data1/jqnvpara_dote00_' + species + '.gda'
    # fnames.append(fname)
    # fname = root_dir + 'data1/jqnvperp_dote00_' + species + '.gda'
    # fnames.append(fname)
    dv = pic_info.dx_di * pic_info.dz_di * pic_info.mime
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    fdata = []
    fdata_1d = []
    for fname in fnames:
        x, z, data = read_2d_fields(pic_info, fname, **kwargs)
        fdata_cum = np.cumsum(np.sum(data, axis=0)) * dv
        fdata_1d.append(fdata_cum)
        data_new = signal.convolve2d(data, kernel, 'same')
        fdata.append(data_new)
    fdata = np.asarray(fdata)
    fdata_1d = np.asarray(fdata_1d)
    fdata /= j0  # Normalization
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    fname = 'jdotes_' + species
    bottom_panel = True
    xlim = srange[:2]
    zlim = srange[2:]
    nlevels_contour = 10
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'bottom_panel': bottom_panel,
        'fdata_1d': fdata_1d,
        'xlim': xlim,
        'zlim': zlim
    }
    jdote_plot = PlotMultiplePanels(**kwargs_plots)
    plt.show()


def plot_jdotes_fields_s(run_name, root_dir, pic_info, species, ct, srange,
                         axis_pos, gaps, fig_sizes):
    """Plot jdote due to different drift current

    This will not use the PlotMultiplePanels class

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        species: particle species.
        ct: current time frame
        srange: spatial range
    """
    ng = 3
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    dmax = []
    dmin = []
    kernel = np.ones((ng, ng)) / float(ng * ng)
    dv = pic_info.dx_di * pic_info.dz_di * pic_info.mime
    fname = root_dir + 'data1/jcpara_dote00_' + species + '.gda'
    x, z, jcpara_dote = read_2d_fields(pic_info, fname, **kwargs)
    jcpara_dote_cum = np.cumsum(np.sum(jcpara_dote, axis=0)) * dv
    dmin.append(np.min(jcpara_dote_cum))
    dmax.append(np.max(jcpara_dote_cum))
    fname = root_dir + 'data1/jgrad_dote00_' + species + '.gda'
    x, z, jgrad_dote = read_2d_fields(pic_info, fname, **kwargs)
    jgrad_dote_cum = np.cumsum(np.sum(jgrad_dote, axis=0)) * dv
    dmin.append(np.min(jgrad_dote_cum))
    dmax.append(np.max(jgrad_dote_cum))
    fname = root_dir + 'data1/jmag_dote00_' + species + '.gda'
    x, z, jmag_dote = read_2d_fields(pic_info, fname, **kwargs)
    jmag_dote_cum = np.cumsum(np.sum(jmag_dote, axis=0)) * dv
    dmin.append(np.min(jmag_dote_cum))
    dmax.append(np.max(jmag_dote_cum))
    fname = root_dir + 'data1/jpolar_dote00_' + species + '.gda'
    x, z, jpolar_dote = read_2d_fields(pic_info, fname, **kwargs)
    jpolar_dote_cum = np.cumsum(np.sum(jpolar_dote, axis=0)) * dv
    dmin.append(np.min(jpolar_dote_cum))
    dmax.append(np.max(jpolar_dote_cum))
    fname = root_dir + 'data1/jagy_dote00_' + species + '.gda'
    x, z, jagy_dote = read_2d_fields(pic_info, fname, **kwargs)
    jagy_dote_cum = np.cumsum(np.sum(jagy_dote, axis=0)) * dv
    dmin.append(np.min(jagy_dote_cum))
    dmax.append(np.max(jagy_dote_cum))
    fname = root_dir + 'data1/jqnvpara_dote00_' + species + '.gda'
    x, z, jqnvpara_dote = read_2d_fields(pic_info, fname, **kwargs)
    jqnvpara_dote_cum = np.cumsum(np.sum(jqnvpara_dote, axis=0)) * dv
    dmin.append(np.min(jqnvpara_dote_cum))
    dmax.append(np.max(jqnvpara_dote_cum))

    min_jdote = min(dmin) * 1.1
    max_jdote = max(dmax) * 1.1

    jcpara_dote = signal.convolve2d(jcpara_dote, kernel, 'same')
    jgrad_dote = signal.convolve2d(jgrad_dote, kernel, 'same')
    jmag_dote = signal.convolve2d(jmag_dote, kernel, 'same')
    jpolar_dote = signal.convolve2d(jpolar_dote, kernel, 'same')
    jagy_dote = signal.convolve2d(jagy_dote, kernel, 'same')
    jqnvpara_dote = signal.convolve2d(jqnvpara_dote, kernel, 'same')

    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    j0 = 0.1 * va**2 * b0
    jcpara_dote /= j0  # Normalization
    jgrad_dote /= j0
    jmag_dote /= j0
    jpolar_dote /= j0
    jagy_dote /= j0
    jqnvpara_dote /= j0
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[9, 8])
    xs0, ys0 = 0.1, 0.7
    w1, h1 = 0.25, 0.28125
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        jqnvpara_dote,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$\boldsymbol{j}_\parallel\cdot\boldsymbol{E}$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)
    xs = xs0 + gap + w1
    ys = ys0
    ax2 = fig.add_axes([xs, ys, w1, h1])
    p2 = ax2.imshow(
        jcpara_dote,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.tick_params(axis='y', labelleft='off')
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.text(
        0.02,
        0.85,
        r'$\boldsymbol{j}_c\cdot\boldsymbol{E}$',
        color=colors[0],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)
    xs = xs + gap + w1
    ax3 = fig.add_axes([xs, ys, w1, h1])
    p3 = ax3.imshow(
        jpolar_dote,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(axis='x', labelbottom='off')
    ax3.tick_params(axis='y', labelleft='off')
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.text(
        0.02,
        0.85,
        r'$\boldsymbol{j}_p\cdot\boldsymbol{E}$',
        color=colors[3],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)

    ys = ys0 - h1 - gap
    ax4 = fig.add_axes([xs0, ys, w1, h1])
    p4 = ax4.imshow(
        jmag_dote,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax4.tick_params(labelsize=16)
    ax4.tick_params(axis='x', labelbottom='off')
    ax4.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax4.set_ylabel(r'$z/d_i$', fontsize=20)
    ax4.text(
        0.02,
        0.85,
        r'$\boldsymbol{j}_m\cdot\boldsymbol{E}$',
        color=colors[2],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax4.transAxes)
    xs = xs0 + gap + w1
    ax5 = fig.add_axes([xs, ys, w1, h1])
    p5 = ax5.imshow(
        jgrad_dote,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax5.tick_params(axis='x', labelbottom='off')
    ax5.tick_params(axis='y', labelleft='off')
    ax5.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax5.text(
        0.02,
        0.85,
        r'$\boldsymbol{j}_g\cdot\boldsymbol{E}$',
        color=colors[2],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax5.transAxes)
    xs = xs + gap + w1
    ax6 = fig.add_axes([xs, ys, w1, h1])
    ax6.tick_params(axis='x', labelbottom='off')
    ax6.tick_params(axis='y', labelleft='off')
    p6 = ax6.imshow(
        jagy_dote,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax6.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax6.text(
        0.02,
        0.85,
        r'$\boldsymbol{j}_a\cdot\boldsymbol{E}$',
        color=colors[4],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax6.transAxes)

    h2 = 2 * h1 + gap
    cbar_ax = fig.add_axes([xs + w1 + 0.01, ys0 - h1 - gap, 0.02, h2])
    cbar1 = fig.colorbar(p1, cax=cbar_ax)
    cbar1.ax.tick_params(labelsize=16)

    ys = ys - h1 - gap
    ax7 = fig.add_axes([xs0, ys, w1, h1])
    p71, = ax7.plot(x, jqnvpara_dote_cum, linewidth=2, color='k')
    p72, = ax7.plot(x, jmag_dote_cum, linewidth=2, color=colors[2])
    p73, = ax7.plot([xmin, xmax], [0, 0], linewidth=0.5, linestyle='--')
    ax7.set_xlabel(r'$x/d_i$', fontsize=20)
    ax7.set_ylabel('Accumulation', fontsize=20)
    ax7.tick_params(labelsize=16)
    ax7.set_xlim([xmin, xmax])
    ax7.set_ylim([min_jdote, max_jdote])
    xs = xs0 + gap + w1
    ax8 = fig.add_axes([xs, ys, w1, h1])
    p81, = ax8.plot(x, jcpara_dote_cum, linewidth=2, color=colors[0])
    p82, = ax8.plot(x, jgrad_dote_cum, linewidth=2, color=colors[1])
    p83, = ax8.plot([xmin, xmax], [0, 0], linewidth=0.5, linestyle='--')
    ax8.set_xlabel(r'$x/d_i$', fontsize=20)
    ax8.tick_params(axis='y', labelleft='off')
    ax8.tick_params(labelsize=16)
    ax8.set_xlim([xmin, xmax])
    ax8.set_ylim([min_jdote, max_jdote])
    xs = xs + gap + w1
    ax9 = fig.add_axes([xs, ys, w1, h1])
    p91, = ax9.plot(x, jpolar_dote_cum, linewidth=2, color=colors[3])
    p92, = ax9.plot(x, jagy_dote_cum, linewidth=2, color=colors[4])
    p93, = ax9.plot([xmin, xmax], [0, 0], linewidth=0.5, linestyle='--')
    ax9.set_xlabel(r'$x/d_i$', fontsize=20)
    ax9.tick_params(axis='y', labelleft='off')
    ax9.tick_params(labelsize=16)
    ax9.set_xlim([xmin, xmax])
    ax9.set_ylim([min_jdote, max_jdote])

    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    # fname = 'jdotes_' + species + str(ct).zfill(3) + '.jpg'
    # fig.savefig(fig_dir + fname, dpi=200)
    fname = 'jdotes_' + species + str(ct).zfill(3) + '.eps'
    fig.savefig(fig_dir + fname)
    plt.show()


def plot_curvb_single(run_name, root_dir, pic_info, srange, ct):
    """Plot the curvature of the magnetic field
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/absB.gda'
    x, z, absB = read_2d_fields(pic_info, fname, **kwargs)
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0

    iabsB2 = 1.0 / absB**2

    bx *= iabsB2
    by *= iabsB2
    bz *= iabsB2
    absB *= iabsB2

    nx, = x.shape
    nz, = z.shape
    curvb_x = np.zeros((nz, nx))
    curvb_y = np.zeros((nz, nx))
    curvb_z = np.zeros((nz, nx))
    curvb_x[:nz - 1, :] = -np.diff(by, axis=0)
    curvb_y[:nz - 1, :] = np.diff(bx, axis=0)
    curvb_y[:, :nx - 1] += np.diff(bz)
    curvb_z[:, :nx - 1] = np.diff(by)

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    fig = plt.figure(figsize=[6, 8])
    xs0, ys0 = 0.15, 0.7
    w1, h1 = 0.375, 0.28125
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    print np.min(curvb_z), np.max(curvb_z)
    p1 = ax1.imshow(
        curvb_x,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$B_x$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)
    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        curvb_y,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$B_y$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)
    ys = ys - h1 - gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        curvb_z,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.set_xlabel(r'$x/d_i$', fontsize=20)
    ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.text(
        0.02,
        0.85,
        r'$B_z$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    xs = xs0 + w1 + 0.06
    # if not os.path.isdir('../img/'):
    #     os.makedirs('../img/')
    # dir = '../img/img_jdotes_apj/'
    # path = '../img/img_jdotes_apj/'
    # if not os.path.isdir(path):
    #     os.makedirs(path)
    # fig_dir = path + run_name + '/'
    # if not os.path.isdir(fig_dir):
    #     os.makedirs(fig_dir)
    # fname = 'emf_' + str(ct).zfill(3) + '.eps'
    # fig.savefig(fig_dir + fname)
    plt.show()


def plot_curvb_multi(run_name, root_dir, pic_info):
    """Plot the curvature of magnetic field for multiple time steps
    """
    # ct = 61
    # srange = np.asarray([105, 135, -15, 15])
    # plot_curvb_single(run_name, root_dir, pic_info, srange, ct)
    # ct = 92
    # srange = np.asarray([107, 154, -25, 25])
    # plot_curvb_single(run_name, root_dir, pic_info, srange, ct)
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    plot_curvb_single(run_name, root_dir, pic_info, srange, ct)


def plot_emfields_single(run_name, root_dir, pic_info, srange, ct):
    """Plot the electromagnetic fields for a single time steps
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ex.gda'
    x, z, ex = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ey.gda'
    x, z, ey = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ez.gda'
    x, z, ez = read_2d_fields(pic_info, fname, **kwargs)
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    e0 = 0.3 * va * b0

    bx /= b0
    by /= b0
    bz /= b0
    ex /= e0
    ey /= e0
    ez /= e0

    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    ex = signal.convolve2d(ex, kernel, 'same')
    ey = signal.convolve2d(ey, kernel, 'same')
    ez = signal.convolve2d(ez, kernel, 'same')

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[6, 8.5])
    xs0, ys0 = 0.15, 0.72
    # w1, h1 = 0.375, 0.28125
    w1, h1 = 0.375, 0.2647
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        bx,
        cmap=plt.cm.jet,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$B_x$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)
    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        by,
        cmap=plt.cm.jet,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$B_y$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)
    ys = ys - h1 - gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        bz,
        cmap=plt.cm.jet,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.set_xlabel(r'$x/d_i$', fontsize=20)
    ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.text(
        0.02,
        0.85,
        r'$B_z$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    ys1 = ys - 0.1
    cax = fig.add_axes([xs0, ys1, w1, 0.02])
    cbar = fig.colorbar(p3, cax=cax, orientation='horizontal')
    cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    cbar.ax.tick_params(labelsize=16)
    xs = xs0 + w1 + gap * 8.0 / 6.0
    ax4 = fig.add_axes([xs, ys0, w1, h1])
    p4 = ax4.imshow(
        ex,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax4.tick_params(axis='y', labelleft='off')
    ax4.tick_params(axis='x', labelbottom='off')
    ax4.tick_params(labelsize=16)
    ax4.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax4.text(
        0.02,
        0.85,
        r'$E_x$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax4.transAxes)
    ys = ys0 - h1 - gap
    ax5 = fig.add_axes([xs, ys, w1, h1])
    p5 = ax5.imshow(
        ey,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax5.tick_params(axis='y', labelleft='off')
    ax5.tick_params(axis='x', labelbottom='off')
    ax5.tick_params(labelsize=16)
    ax5.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax5.text(
        0.02,
        0.85,
        r'$E_y$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax5.transAxes)
    ys = ys - h1 - gap
    ax6 = fig.add_axes([xs, ys, w1, h1])
    p6 = ax6.imshow(
        ez,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax6.tick_params(axis='y', labelleft='off')
    ax6.tick_params(labelsize=16)
    ax6.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax6.set_xlabel(r'$x/d_i$', fontsize=20)
    ax6.text(
        0.02,
        0.85,
        r'$E_z$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax6.transAxes)
    ys1 = ys - 0.1
    cax = fig.add_axes([xs, ys1, w1, 0.02])
    cbar = fig.colorbar(p6, cax=cax, orientation='horizontal')
    cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    cbar.ax.tick_params(labelsize=16)
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    fname = 'emf_' + str(ct).zfill(3) + '.eps'
    fig.savefig(fig_dir + fname)
    plt.show()


def plot_emfields_multi(run_name, root_dir, pic_info):
    """Plot the electromagnetic fields for multiple time steps
    """
    # ct = 61
    # srange = np.asarray([104, 134, -15, 15])
    # plot_emfields_single(run_name, root_dir, pic_info, srange, ct)
    ct = 92
    srange = np.asarray([107, 154, -25, 25])
    plot_emfields_single(run_name, root_dir, pic_info, srange, ct)
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    plot_emfields_single(run_name, root_dir, pic_info, srange, ct)


def plot_gradB_single(run_name, root_dir, pic_info, srange, ct):
    """Plot the electromagnetic fields for a single time steps
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    fname = root_dir + 'data/absB.gda'
    x, z, absB = read_2d_fields(pic_info, fname, **kwargs)
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    e0 = 0.3 * va * b0

    absB /= b0
    gradBx = np.diff(absB, axis=1)
    gradBz = np.diff(absB, axis=0)
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    gradBx = signal.convolve2d(gradBx, kernel, 'same')
    gradBz = signal.convolve2d(gradBz, kernel, 'same')

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -0.02, 0.02
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[8, 4])
    xs0, ys0 = 0.13, 0.15
    w1, h1 = 0.4, 0.8
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        gradBx,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.set_xlabel(r'$x/d_i$', fontsize=20)
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$\nabla_x B$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)
    xs = xs0 + w1 + gap
    ax2 = fig.add_axes([xs, ys0, w1, h1])
    p2 = ax2.imshow(
        gradBz,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(axis='y', labelleft='off')
    ax2.tick_params(labelsize=16)
    ax2.set_xlabel(r'$x/d_i$', fontsize=20)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.text(
        0.02,
        0.85,
        r'$\nabla_z B$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)
    # cax = fig.add_axes([xs, ys1, w1, 0.02])
    # cbar = fig.colorbar(p3, cax=cax, orientation='horizontal')
    # cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    # cbar.ax.tick_params(labelsize=16)
    plt.show()


def plot_gradB_multi(run_name, root_dir, pic_info):
    """Plot the gradient B for multiple time steps
    """
    # ct = 61
    # srange = np.asarray([104, 134, -15, 15])
    # plot_gradB_single(run_name, root_dir, pic_info, srange, ct)
    # ct = 92
    # srange = np.asarray([107, 154, -25, 25])
    # plot_gradB_single(run_name, root_dir, pic_info, srange, ct)
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    plot_gradB_single(run_name, root_dir, pic_info, srange, ct)


def plot_ppara_pperp(run_name, root_dir, pic_info, srange, ct):
    """Plot the parallel and perpendicular pressure for a single time steps
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    fname = root_dir + 'data1/ppara_real00_e.gda'
    x, z, ppara_e = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data1/pperp_real00_e.gda'
    x, z, pperp_e = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data1/ppara_real00_i.gda'
    x, z, ppara_i = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data1/pperp_real00_i.gda'
    x, z, pperp_i = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    pnorm = 0.25 * va**2

    ppara_e /= pnorm
    pperp_e /= pnorm
    ppara_i /= pnorm
    pperp_i /= pnorm

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin = np.min([ppara_e, pperp_e, ppara_i, pperp_i])
    vmax = np.max([ppara_e, pperp_e, ppara_i, pperp_i])
    vmin, vmax = 0.1, 100
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[6, 6])
    xs0, ys0 = 0.15, 0.6
    w1, h1 = 0.375, 0.375
    gap = 0.05
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        ppara_e,
        cmap=plt.cm.hot,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='white', linewidths=0.5)
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$P_{e\parallel}$',
        color='w',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)
    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        pperp_e,
        cmap=plt.cm.hot,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='white', linewidths=0.5)
    ax2.set_xlabel(r'$x/d_i$', fontsize=20)
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$P_{e\perp}$',
        color='w',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)
    xs = xs0 + w1 + gap
    ax3 = fig.add_axes([xs, ys0, w1, h1])
    p3 = ax3.imshow(
        ppara_i,
        cmap=plt.cm.hot,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(axis='x', labelbottom='off')
    ax3.tick_params(axis='y', labelleft='off')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='white', linewidths=0.5)
    ax3.text(
        0.02,
        0.85,
        r'$P_{i\parallel}$',
        color='w',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    ys = ys0 - h1 - gap
    ax4 = fig.add_axes([xs, ys, w1, h1])
    p4 = ax4.imshow(
        pperp_i,
        cmap=plt.cm.hot,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax4.tick_params(labelsize=16)
    ax4.tick_params(axis='y', labelleft='off')
    ax4.contour(x, z, Ay, colors='white', linewidths=0.5)
    ax4.set_xlabel(r'$x/d_i$', fontsize=20)
    ax4.text(
        0.02,
        0.85,
        r'$P_{i\perp}$',
        color='w',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax4.transAxes)
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    fname = 'pre_' + str(ct).zfill(3) + '.eps'
    fig.savefig(fig_dir + fname)
    plt.show()


def plot_ppara_pperp_multi(run_name, root_dir, pic_info):
    """Plot the parallel and perpendicular pressure for multiple time steps
    """
    ct = 61
    srange = np.asarray([105, 135, -15, 15])
    plot_ppara_pperp(run_name, root_dir, pic_info, srange, ct)
    ct = 92
    srange = np.asarray([107, 154, -25, 25])
    plot_ppara_pperp(run_name, root_dir, pic_info, srange, ct)
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    plot_ppara_pperp(run_name, root_dir, pic_info, srange, ct)


def plot_jdrifts_dote_fields():
    ct = 61
    srange = np.asarray([104, 134, -15, 15])
    xs, ys = 0.22, 0.85
    w1, h1 = 0.65, 0.14
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.02]
    fig_sizes = (4, 12)
    plot_jdotes_fields_s(run_name, root_dir, pic_info, 'e', ct, srange,
                         axis_pos, gaps, fig_sizes)

    # ct = 101
    # srange = np.asarray([110, 170, -25, 25])
    # xs, ys = 0.22, 0.85
    # w1, h1 = 0.65, 0.14
    # axis_pos = [xs, ys, w1, h1]
    # gaps = [0.1, 0.02]
    # fig_sizes = (4, 12)
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange,
    #         axis_pos, gaps, fig_sizes)

    # ct = 170
    # srange = np.asarray([150, 200, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'e', ct, srange)

    # ct = 48
    # xs, ys = 0.22, 0.85
    # w1, h1 = 0.65, 0.14
    # axis_pos = [xs, ys, w1, h1]
    # gaps = [0.1, 0.02]
    # fig_sizes = (4, 12)
    # srange = np.asarray([80, 100, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange,
    #         axis_pos, gaps, fig_sizes)

    # ct = 92
    # xs, ys = 0.22, 0.85
    # w1, h1 = 0.65, 0.14
    # axis_pos = [xs, ys, w1, h1]
    # gaps = [0.1, 0.02]
    # fig_sizes = (4, 6)
    # srange = np.asarray([107, 154, -25, 25])
    # # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange,
    # #         axis_pos, gaps, fig_sizes)
    # plot_jdotes_fields_s(run_name, root_dir, pic_info, 'e', ct, srange,
    #         axis_pos, gaps, fig_sizes)

    # ct = 206
    # srange = np.asarray([150, 200, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'e', ct, srange)

    # ct = 55
    # xs, ys = 0.22, 0.85
    # w1, h1 = 0.65, 0.14
    # axis_pos = [xs, ys, w1, h1]
    # gaps = [0.1, 0.02]
    # fig_sizes = (4, 12)
    # srange = np.asarray([110, 130, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange,
    #         axis_pos, gaps, fig_sizes)

    # ct = 110
    # srange = np.asarray([110, 180, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'e', ct, srange)
    # ct = 200
    # srange = np.asarray([130, 200, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange)
    # ct = 40
    # srange = np.asarray([80, 100, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange)
    # ct = 80
    # srange = np.asarray([100, 150, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange)
    # ct = 200
    # srange = np.asarray([150, 200, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'i', ct, srange)

    # ct = 109
    # xs, ys = 0.18, 0.85
    # w1, h1 = 0.68, 0.14
    # axis_pos = [xs, ys, w1, h1]
    # gaps = [0.1, 0.02]
    # fig_sizes = (5, 12)
    # srange = np.asarray([120, 200, -25, 25])
    # plot_jdotes_fields(run_name, root_dir, pic_info, 'e', ct, srange,
    #         axis_pos, gaps, fig_sizes)

    # ct = 55
    # xs, ys = 0.18, 0.85
    # w1, h1 = 0.68, 0.14
    # axis_pos = [xs, ys, w1, h1]
    # gaps = [0.1, 0.02]
    # fig_sizes = (5, 12)
    # srange = np.asarray([145, 185, -20, 20])
    # plot_jdotes_fields_s(run_name, root_dir, pic_info, 'e', ct, srange,
    #         axis_pos, gaps, fig_sizes)


def plot_fields_wcuts(run_name, root_dir, pic_info, ct, srange, xcp,
                      label_name, dnorm, fdata):
    """Plot 2D fields with cuts

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        ct: current time frame
        srange: spatial range
        xcp: the cut x positions
        label_name: the label name of the dataset
        dnorm: the normalization for the data
        fdata: field data
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    dv = pic_info.dx_di * pic_info.dz_di * pic_info.mime
    fdata = signal.convolve2d(fdata, kernel, 'same')

    fdata /= dnorm
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    dx = x[1] - x[0]
    dz = z[1] - z[0]
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[10, 5])
    xs0, ys0 = 0.12, 0.14
    w1, h1 = 0.4, 0.8
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        fdata,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.set_xlabel(r'$x/d_i$', fontsize=20)
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        label_name,
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)

    # Plot a cut along the vertical direction
    xcp_index = (xcp - srange[0]) / dx
    ax1.set_color_cycle(colors)
    for ix in xcp_index:
        ax1.plot([x[ix], x[ix]], [zmin, zmax], linewidth=0.5, linestyle='--')
    xs = xs0 + w1 + gap
    w2 = w1
    ax2 = fig.add_axes([xs, ys0, w2, h1])
    ax2.set_color_cycle(colors)
    for ix in xcp_index:
        cdata = fdata[:, ix]
        ax2.plot(cdata, z, linewidth=2)
    ax2.tick_params(axis='y', labelleft='off')
    ax2.tick_params(labelsize=16)
    ax2.set_ylim([zmin, zmax])
    plt.show()


def plot_jdotes_xyz(run_name, root_dir, pic_info, ct, srange, xcp, jdote_x,
                    jdote_y, jdote_z, dnorm):
    """Plot energy conversion due to 3 components of the currents

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        ct: current time frame
        srange: spatial range
        xcp: the cut x positions
        jdote_x, jdote_y, jdote_z: energy conversion
        dnorm: the normalization for the data
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    dv = pic_info.dx_di * pic_info.dz_di * pic_info.mime
    jdote_x_cum = np.cumsum(np.sum(jdote_x, axis=0)) * dv
    jdote_y_cum = np.cumsum(np.sum(jdote_y, axis=0)) * dv
    jdote_z_cum = np.cumsum(np.sum(jdote_z, axis=0)) * dv
    jdote_x = signal.convolve2d(jdote_x, kernel, 'same')
    jdote_y = signal.convolve2d(jdote_y, kernel, 'same')
    jdote_z = signal.convolve2d(jdote_z, kernel, 'same')

    jdote_x /= dnorm
    jdote_y /= dnorm
    jdote_z /= dnorm
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)

    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    dx = x[1] - x[0]
    dz = z[1] - z[0]
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[5, 10])
    xs0, ys0 = 0.17, 0.78
    w1, h1 = 0.4, 0.2
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        jdote_x,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$j_xE_x$',
        color=colors[0],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)
    # Plot a cut along the vertical direction
    xcp_index = (xcp - srange[0]) / dx
    ax1.set_color_cycle(colors)
    for ix in xcp_index:
        ax1.plot([x[ix], x[ix]], [zmin, zmax], linewidth=0.5, linestyle='--')
    xs = xs0 + w1
    w2 = w1
    ax12 = fig.add_axes([xs, ys0, w2, h1])
    ax12.set_color_cycle(colors)
    for ix in xcp_index:
        cdata = jdote_x[:, ix]
        ax12.plot(cdata, z, linewidth=2)
    ax12.set_xlim([-1, 1])
    ax12.set_ylim([zmin, zmax])
    ax12.tick_params(axis='x', labelbottom='off')
    ax12.tick_params(axis='y', labelleft='off')
    ax12.tick_params(labelsize=16)

    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        jdote_y,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$j_yE_y$',
        color=colors[1],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)
    ax2.set_color_cycle(colors)
    for ix in xcp_index:
        ax2.plot([x[ix], x[ix]], [zmin, zmax], linewidth=0.5, linestyle='--')
    ax22 = fig.add_axes([xs, ys, w1, h1])
    ax22.set_color_cycle(colors)
    for ix in xcp_index:
        cdata = jdote_y[:, ix]
        ax22.plot(cdata, z, linewidth=2)
    ax22.set_xlim([-1, 1])
    ax22.set_ylim([zmin, zmax])
    ax22.tick_params(axis='x', labelbottom='off')
    ax22.tick_params(axis='y', labelleft='off')
    ax22.tick_params(labelsize=16)

    ys -= h1 + gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        jdote_z,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.tick_params(axis='x', labelbottom='off')
    ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.text(
        0.02,
        0.85,
        r'$j_zE_z$',
        color=colors[2],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    ax3.set_color_cycle(colors)
    for ix in xcp_index:
        ax3.plot([x[ix], x[ix]], [zmin, zmax], linewidth=0.5, linestyle='--')
    ax32 = fig.add_axes([xs, ys, w1, h1])
    ax32.set_color_cycle(colors)
    for ix in xcp_index:
        cdata = jdote_z[:, ix]
        ax32.plot(cdata, z, linewidth=2)
    ax32.set_xlim([-1, 1])
    ax32.set_ylim([zmin, zmax])
    ax32.tick_params(axis='y', labelleft='off')
    ax32.tick_params(labelsize=16)

    ys -= h1 + gap
    ax4 = fig.add_axes([xs0, ys, w1, h1])
    ax4.set_color_cycle(colors)
    ax4.plot(x, jdote_x_cum, linewidth=2)
    ax4.plot(x, jdote_y_cum, linewidth=2)
    ax4.plot(x, jdote_z_cum, linewidth=2)
    ax4.plot([xmin, xmax], [0, 0], linewidth=0.5, color='k', linestyle='--')
    ax4.set_xlim([xmin, xmax])
    ax4.tick_params(labelsize=16)
    ax4.set_xlabel(r'$x/d_i$', fontsize=20)

    # plt.show()


def plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, species):
    """Plot jdote due to a single current
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    jdote_norm = 0.1 * va**2 * b0
    fname = root_dir + 'data/ex.gda'
    x, z, ex = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ey.gda'
    x, z, ey = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ez.gda'
    x, z, ez = read_2d_fields(pic_info, fname, **kwargs)
    data_dir = 'data1'
    jtypes = ['jqnvpara', 'jcpara', 'jgrad', 'jmag', 'jpolar', 'jagy']
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    for jtype in jtypes:
        dname = jtype + 'x00_' + species
        fname = root_dir + data_dir + '/' + dname + '.gda'
        x, z, jqnvpara_x = read_2d_fields(pic_info, fname, **kwargs)
        dname = jtype + 'y00_' + species
        fname = root_dir + data_dir + '/' + dname + '.gda'
        x, z, jqnvpara_y = read_2d_fields(pic_info, fname, **kwargs)
        dname = jtype + 'z00_' + species
        fname = root_dir + data_dir + '/' + dname + '.gda'
        x, z, jqnvpara_z = read_2d_fields(pic_info, fname, **kwargs)
        jdote_x = jqnvpara_x * ex
        jdote_y = jqnvpara_y * ey
        jdote_z = jqnvpara_z * ez
        plot_jdotes_xyz(run_name, root_dir, pic_info, ct, srange, xcp, jdote_x,
                        jdote_y, jdote_z, jdote_norm)
        fname = jtype + '_' + str(ct).zfill(3) + '_' + species + '.eps'
        plt.savefig(fig_dir + fname)
        plt.close()
        # plt.show()


def plot_jdotes_multi(run_name, root_dir, pic_info):
    """Plot jdote due to currents at multiple time step
    """
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    xcp = [155, 165, 175]
    plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, 'e')
    plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')
    ct = 61
    srange = np.asarray([105, 135, -15, 15])
    xcp = [115, 125]
    plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, 'e')
    plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')
    ct = 92
    srange = np.asarray([107, 154, -25, 25])
    xcp = [115, 125, 135, 145]
    plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, 'e')
    plot_jdotes_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')


def plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, species):
    """Plot ux, uy, uz for a single time step
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    fname = root_dir + 'data/u' + species + 'x.gda'
    x, z, ux = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/u' + species + 'y.gda'
    x, z, uy = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/u' + species + 'z.gda'
    x, z, uz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    absB2 = bx**2 + by**2 + bz**2
    udotb = (ux * bx + uy * by + uz * bz) / absB2
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    ux = udotb * bx / va
    uy = udotb * by / va
    uz = udotb * bz / va
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    dx = x[1] - x[0]
    dz = z[1] - z[0]
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[3, 8])
    xs0, ys0 = 0.17, 0.7
    w1, h1 = 0.75, 0.28125
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        ux,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$v_x$',
        color=colors[0],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)

    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        uy,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$v_y$',
        color=colors[1],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)

    ys -= h1 + gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        uz,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.set_xlabel(r'$x/d_i$', fontsize=20)
    ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.text(
        0.02,
        0.85,
        r'$v_z$',
        color=colors[2],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    # plt.close()
    plt.show()


def plot_bulku_single(run_name, root_dir, pic_info, srange, ct, xcp):
    """Plot ux, uy, uz for single fluid a single time step
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    fname = root_dir + 'data/uex.gda'
    x, z, uex = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/uey.gda'
    x, z, uey = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/uez.gda'
    x, z, uez = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ne.gda'
    x, z, ne = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/uix.gda'
    x, z, uix = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/uiy.gda'
    x, z, uiy = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/uiz.gda'
    x, z, uiz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ni.gda'
    x, z, ni = read_2d_fields(pic_info, fname, **kwargs)
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    mime = pic_info.mime
    ntot = ne + ni * mime
    ux = (uex * ne + uix * ni * mime) / ntot
    uy = (uey * ne + uiy * ni * mime) / ntot
    uz = (uez * ne + uiz * ni * mime) / ntot
    u0 = 0.5 * va
    ux /= u0
    uy /= u0
    uz /= u0
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    dx = x[1] - x[0]
    dz = z[1] - z[0]
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[3, 8.5])
    xs0, ys0 = 0.03 * 8 / 3, 0.72
    w1, h1 = 0.75, 0.2647
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        ux,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.tick_params(axis='y', labelleft='off')
    ax1.tick_params(axis='x', labelbottom='off')
    # ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$v_x$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)

    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        uy,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.tick_params(axis='y', labelleft='off')
    ax2.tick_params(axis='x', labelbottom='off')
    # ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$v_y$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)

    ys -= h1 + gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        uz,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.set_xlabel(r'$x/d_i$', fontsize=20)
    # ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.tick_params(axis='y', labelleft='off')
    ax3.text(
        0.02,
        0.85,
        r'$v_z$',
        color='k',
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    ys1 = ys - 0.1
    cax = fig.add_axes([xs0, ys1, w1, 0.02])
    cbar = fig.colorbar(p3, cax=cax, orientation='horizontal')
    cbar.set_ticks(np.arange(-0.8, 0.9, 0.4))
    cbar.ax.tick_params(labelsize=16)
    fname = 'bulku_' + str(ct).zfill(3) + '.eps'
    fig.savefig(fig_dir + fname)
    # plt.close()
    plt.show()


def plot_uxyz_multi(run_name, root_dir, pic_info):
    """Plot ux, uy, uz for multiple time steps
    """
    # ct = 55
    # srange = np.asarray([145, 185, -20, 20])
    # xcp = [155, 165, 175]
    # plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')
    # plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')
    ct = 61
    srange = np.asarray([104, 134, -15, 15])
    xcp = [115, 125]
    plot_bulku_single(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')
    # plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')
    # ct = 92
    # srange = np.asarray([107, 154, -25, 25])
    # xcp = [115, 125, 135, 145]
    # plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, 'e')
    # plot_uxyz_single(run_name, root_dir, pic_info, srange, ct, xcp, 'i')


def plot_epara_xyz_single(run_name, root_dir, pic_info, srange, ct, xcp):
    """Plot parallel electric field for a single time step
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    e0 = 0.1 * b0 * va
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ex.gda'
    x, z, ex = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ey.gda'
    x, z, ey = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ez.gda'
    x, z, ez = read_2d_fields(pic_info, fname, **kwargs)
    absB2 = bx**2 + by**2 + bz**2
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    edotb = (ex * bx + ey * by + ez * bz) / absB2
    eparax = edotb * bx / e0
    eparay = edotb * by / e0
    eparaz = edotb * bz / e0
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    eparax = signal.convolve2d(eparax, kernel, 'same')
    eparay = signal.convolve2d(eparay, kernel, 'same')
    eparaz = signal.convolve2d(eparaz, kernel, 'same')
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    dx = x[1] - x[0]
    dz = z[1] - z[0]
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[3, 8])
    xs0, ys0 = 0.17, 0.7
    w1, h1 = 0.75, 0.28125
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        eparax,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$E_{\parallel x}$',
        color=colors[0],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)

    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        eparay,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$E_{\parallel y}$',
        color=colors[1],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)

    ys -= h1 + gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        eparaz,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.set_xlabel(r'$x/d_i$', fontsize=20)
    ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.text(
        0.02,
        0.85,
        r'$E_{\parallel z}$',
        color=colors[2],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    # plt.close()
    plt.show()


def plot_epara_xyz_multi(run_name, root_dir, pic_info):
    """Plot parallel electric field for multiple time steps
    """
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    xcp = [155, 165, 175]
    plot_epara_xyz_single(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_epara_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # ct = 61
    # srange = np.asarray([105, 135, -15, 15])
    # xcp = [115, 125]
    # plot_epara_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_epara_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # ct = 92
    # srange = np.asarray([107, 154, -25, 25])
    # xcp = [115, 125, 135, 145]
    # plot_epara_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_epara_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)


def plot_eperp_xyz_single(run_name, root_dir, pic_info, srange, ct, xcp):
    """Plot perpendicular electric field for a single time step
    """
    kwargs = {
        "current_time": ct,
        "xl": srange[0],
        "xr": srange[1],
        "zb": srange[2],
        "zt": srange[3]
    }
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    b0 = pic_info.b0
    e0 = 0.5 * b0 * va
    fname = root_dir + 'data/bx.gda'
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/by.gda'
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/bz.gda'
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ex.gda'
    x, z, ex = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ey.gda'
    x, z, ey = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + 'data/ez.gda'
    x, z, ez = read_2d_fields(pic_info, fname, **kwargs)
    absB2 = bx**2 + by**2 + bz**2
    fname2 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname2, **kwargs)
    edotb = (ex * bx + ey * by + ez * bz) / absB2
    eperpx = (ex - edotb * bx) / e0
    eperpy = (ey - edotb * by) / e0
    eperpz = (ez - edotb * bz) / e0
    ng = 3
    kernel = np.ones((ng, ng)) / float(ng * ng)
    eperpx = signal.convolve2d(eperpx, kernel, 'same')
    eperpy = signal.convolve2d(eperpy, kernel, 'same')
    eperpz = signal.convolve2d(eperpz, kernel, 'same')
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    dir = '../img/img_jdotes_apj/'
    path = '../img/img_jdotes_apj/'
    if not os.path.isdir(path):
        os.makedirs(path)
    fig_dir = path + run_name + '/'
    if not os.path.isdir(fig_dir):
        os.makedirs(fig_dir)
    xmin, xmax = np.min(x), np.max(x)
    zmin, zmax = np.min(z), np.max(z)
    vmin, vmax = -1.0, 1.0
    dx = x[1] - x[0]
    dz = z[1] - z[0]
    nx, = x.shape
    nz, = z.shape
    fig = plt.figure(figsize=[3, 8])
    xs0, ys0 = 0.17, 0.7
    w1, h1 = 0.75, 0.28125
    gap = 0.03
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    p1 = ax1.imshow(
        eperpx,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax1.tick_params(labelsize=16)
    ax1.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax1.tick_params(axis='x', labelbottom='off')
    ax1.set_ylabel(r'$z/d_i$', fontsize=20)
    ax1.text(
        0.02,
        0.85,
        r'$E_{\perp x}$',
        color=colors[0],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax1.transAxes)

    ys = ys0 - h1 - gap
    ax2 = fig.add_axes([xs0, ys, w1, h1])
    p2 = ax2.imshow(
        eperpy,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax2.tick_params(labelsize=16)
    ax2.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax2.tick_params(axis='x', labelbottom='off')
    ax2.set_ylabel(r'$z/d_i$', fontsize=20)
    ax2.text(
        0.02,
        0.85,
        r'$E_{\perp y}$',
        color=colors[1],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax2.transAxes)

    ys -= h1 + gap
    ax3 = fig.add_axes([xs0, ys, w1, h1])
    p3 = ax3.imshow(
        eperpz,
        cmap=plt.cm.seismic,
        extent=[xmin, xmax, zmin, zmax],
        aspect='auto',
        origin='lower',
        vmin=vmin,
        vmax=vmax,
        interpolation='bicubic')
    ax3.tick_params(labelsize=16)
    ax3.contour(x, z, Ay, colors='black', linewidths=0.5)
    ax3.set_xlabel(r'$x/d_i$', fontsize=20)
    ax3.set_ylabel(r'$z/d_i$', fontsize=20)
    ax3.text(
        0.02,
        0.85,
        r'$E_{\perp z}$',
        color=colors[2],
        fontsize=20,
        bbox=dict(
            facecolor='none', alpha=1.0, edgecolor='none', pad=10.0),
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax3.transAxes)
    # plt.close()
    plt.show()


def plot_eperp_xyz_multi(run_name, root_dir, pic_info):
    """Plot perpendicular electric field for multiple time steps
    """
    ct = 55
    srange = np.asarray([145, 185, -20, 20])
    xcp = [155, 165, 175]
    plot_eperp_xyz_single(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_eperp_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # ct = 61
    # srange = np.asarray([105, 135, -15, 15])
    # xcp = [115, 125]
    # plot_eperp_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_eperp_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # ct = 92
    # srange = np.asarray([107, 154, -25, 25])
    # xcp = [115, 125, 135, 145]
    # plot_eperp_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)
    # plot_eperp_xyz_multi(run_name, root_dir, pic_info, srange, ct, xcp)


def plot_spectra_electron():
    """Plot electron spectra for multiple runs

    """
    species = 'e'
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    img_dir = '../img/spectra/'
    if not os.path.isdir(img_dir):
        os.makedirs(img_dir)
    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    ax.set_color_cycle(colors)
    base_dirs, run_names = ApJ_long_paper_runs()
    nruns = len(run_names)
    shift = 1
    offset = [50, 80, 50, 50]
    extent = [10, 40, 100, 110]
    run = 0
    e_extend = 20
    colors_plot = []
    for run_name in run_names[:4]:
        picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
        pic_info = read_data_from_json(picinfo_fname)
        dir = '../data/spectra/' + run_name + '/'
        n0 = pic_info.nx * pic_info.ny * pic_info.nz * pic_info.nppc
        ct = 1
        fname = dir + 'spectrum-' + species + '.1'
        file_exist = os.path.isfile(fname)
        while file_exist:
            ct += 1
            fname = dir + 'spectrum-' + species + '.' + str(ct)
            file_exist = os.path.isfile(fname)
        fname = dir + 'spectrum-' + species + '.' + str(ct - 1)
        elin, flin, elog, flog = get_energy_distribution(fname, n0)
        elog_norm = get_normalized_energy(species, elog, pic_info)
        flog *= shift
        p1, = ax.loglog(elog_norm, flog, linewidth=2)
        power_fit = power_law_fit(elog, flog, offset[run], extent[run])
        es, ee = power_fit.es, power_fit.ee
        fpower = power_fit.fpower
        color = p1.get_color()
        es -= e_extend
        ee += e_extend
        powerIndex = "{%0.2f}" % power_fit.params[0]
        pname = r'$\sim \varepsilon^{' + powerIndex + '}$'
        if run > 0:
            p23, = ax.loglog(
                elog_norm[es:ee],
                fpower[es:ee] * 2,
                color=color,
                linestyle='--',
                linewidth=2,
                label=pname)
            colors_plot.append(color)
        # # Help for fitting
        # p21, = ax.loglog(elog_norm[es], flog[es], marker='.', markersize=10,
        #         linestyle='None', color=color)
        # p22, = ax.loglog(elog_norm[ee], flog[ee], marker='.', markersize=10,
        #         linestyle='None', color=color)
        # p23, = ax.loglog(elog_norm, fpower)
        ax.set_xlim([1E-1, 4E3])
        ax.set_ylim([1E-8, 1E4])
        shift *= 5
        run += 1

    fpower = elog_norm**-5
    ax.loglog(elog_norm, fpower * 1E11)

    ax.set_xlabel(
        r'$\varepsilon/\varepsilon_\text{th}$', fontdict=font, fontsize=24)
    ax.set_ylabel(r'$f(\varepsilon)$', fontdict=font, fontsize=24)
    ax.tick_params(labelsize=20)
    leg = ax.legend(
        loc=3,
        prop={'size': 20},
        ncol=1,
        shadow=False,
        fancybox=False,
        frameon=False)
    for color, text in zip(colors_plot, leg.get_texts()):
        text.set_color(color)
    ax.text(
        0.5,
        0.05,
        'R8',
        color=colors[0],
        fontsize=20,
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax.transAxes)
    ax.text(
        0.6,
        0.05,
        'R7',
        color=colors[1],
        fontsize=20,
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax.transAxes)
    ax.text(
        0.7,
        0.05,
        'R1',
        color=colors[2],
        fontsize=20,
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax.transAxes)
    ax.text(
        0.85,
        0.05,
        'R6',
        color=colors[3],
        fontsize=20,
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax.transAxes)

    plt.show()


def plot_spectra_R1_R5():
    """Plot electron spectra for run R1 and R5

    """
    species = 'e'
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    img_dir = '../img/spectra/'
    if not os.path.isdir(img_dir):
        os.makedirs(img_dir)
    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    ax.set_color_cycle(colors)
    run_names = ['mime25_beta002', 'mime100_beta002']
    labels = [r'R1: $c_A/c=0.2, m_i/m_e=25$', r'R5: $c_A/c=0.1, m_i/m_e=100$']
    for run_name, label in zip(run_names, labels):
        picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
        pic_info = read_data_from_json(picinfo_fname)
        dir = '../data/spectra/' + run_name + '/'
        n0 = pic_info.nx * pic_info.ny * pic_info.nz * pic_info.nppc
        ct = 1
        fname = dir + 'spectrum-' + species + '.1'
        file_exist = os.path.isfile(fname)
        while file_exist:
            ct += 1
            fname = dir + 'spectrum-' + species + '.' + str(ct)
            file_exist = os.path.isfile(fname)
        fname = dir + 'spectrum-' + species + '.' + str(ct - 1)
        elin, flin, elog, flog = get_energy_distribution(fname, n0)
        elog_norm = get_normalized_energy(species, elog, pic_info)
        ax.loglog(elog_norm, flog, linewidth=3, label=label)

    ax.set_xlim([1E-1, 4E2])
    ax.set_ylim([1E-8, 1E2])
    ax.set_xlabel(
        r'$\varepsilon/\varepsilon_\text{th}$', fontdict=font, fontsize=24)
    ax.set_ylabel(r'$f(\varepsilon)$', fontdict=font, fontsize=24)
    ax.tick_params(labelsize=20)
    leg = ax.legend(
        loc=3,
        prop={'size': 20},
        ncol=1,
        shadow=False,
        fancybox=False,
        frameon=False)

    plt.show()


def fit_thermal_core(ene, f):
    """
    """
    estart = 0
    ng = 3
    kernel = np.ones(ng) / float(ng)
    fnew = np.convolve(f, kernel, 'same')
    eend = np.argmax(fnew) + 10  # 10 grids shift for fitting thermal core.
    popt, pcov = curve_fit(fitting_funcs.func_maxwellian, ene[estart:eend],
                           f[estart:eend])
    fthermal = fitting_funcs.func_maxwellian(ene, popt[0], popt[1])
    print 'Energy with maximum flux: ', ene[eend - 10]
    print 'Energy with maximum flux in fitted thermal core: ', 0.5 / popt[1]
    print 'Thermal core fitting coefficients: '
    print popt
    print '---------------------------------------------------------------'
    return (fthermal, popt)


def fit_nonthermal_thermal(ene, f):
    """Fit nonthermal distribution as thermal

    Args:
        ene: the energy bins array.
        f: the particle flux distribution.

    Returns:
        fthermal: thermal part of the particle distribution.
    """
    print('Fitting nonthermal distribution as thermal distribution')
    emax = ene[np.argmax(f)]
    fthermal = fitting_funcs.func_maxwellian(ene, 1.0, 1.0 / (2 * emax))
    ratio = f[np.argmax(f)] / fthermal[np.argmax(f)]
    fthermal *= ratio
    return fthermal


def fit_two_maxwellian():
    """fit the spectrum with two Maxwellian

    """
    species = 'e'
    if not os.path.isdir('../img/'):
        os.makedirs('../img/')
    img_dir = '../img/spectra/'
    if not os.path.isdir(img_dir):
        os.makedirs(img_dir)
    fig = plt.figure(figsize=[7, 8])
    xs, ys = 0.15, 0.35
    w1, h1 = 0.8, 0.6
    ax = fig.add_axes([xs, ys, w1, h1])
    ax.set_color_cycle(colors)
    # pic_info = pic_information.get_pic_info('../../')
    # dir = '../spectrum/'
    # run_name = 'mime25_beta002'
    # run_name = 'mime25_beta0007'
    run_name = 'mime25_beta0001'
    picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    dir = '../data/spectra/' + run_name + '/'
    n0 = pic_info.nx * pic_info.ny * pic_info.nz * pic_info.nppc
    ct = 1
    fname = dir + 'spectrum-' + species + '.1'
    file_exist = os.path.isfile(fname)
    while file_exist:
        ct += 1
        fname = dir + 'spectrum-' + species + '.' + str(ct)
        file_exist = os.path.isfile(fname)
    fname = dir + 'spectrum-' + species + '.' + str(ct - 1)
    elin, flin, elog, flog = get_energy_distribution(fname, n0)
    elog_norm = get_normalized_energy(species, elog, pic_info)
    fthermal, popt = fit_thermal_core(elog, flog)
    fnonthermal = flog - fthermal
    # fthermal1 = fit_nonthermal_thermal(elog, fnonthermal)
    imax = np.argmax(fnonthermal)
    ns = imax + 20
    fthermal1, popt = fit_thermal_core(elog[ns:], fnonthermal[ns:])
    fthermal1 = fitting_funcs.func_maxwellian(elog, popt[0], popt[1])
    fnonthermal1 = fnonthermal - fthermal1
    imax = np.argmax(fnonthermal1)
    ns = imax + 20
    fthermal2, popt = fit_thermal_core(elog[ns:], fnonthermal1[ns:])
    fthermal2 = fitting_funcs.func_maxwellian(elog, popt[0], popt[1])
    fnonthermal2 = fnonthermal1 - fthermal2
    # fthermal_tot = fthermal + fthermal1 + fthermal2
    fthermal_tot = fthermal + fthermal1
    norm = fthermal_tot[1] / flog[1]
    fthermal_tot /= norm
    fthermal /= norm
    fthermal1 /= norm
    fthermal2 /= norm
    nbins, = flog.shape
    error_re = np.zeros(nbins)
    index = np.nonzero(flog)
    error_re[index] = (fthermal_tot[index] - flog[index]) / flog[index]

    ax.loglog(elog, flog, linewidth=4, label='simulation')
    ax.loglog(elog, fthermal_tot, linewidth=2, label='fitted')
    ax.loglog(elog, fnonthermal1, linewidth=2, label='Nonthermal')
    ax.loglog(elog, fthermal, linewidth=1, linestyle='--', label='thermal1')
    ax.loglog(elog, fthermal1, linewidth=1, linestyle='--', label='thermal2')
    # ax.loglog(elog, fthermal2, linewidth=1, linestyle='--', label='thermal3')
    # ax.loglog(elog, fnonthermal, linewidth=3)
    # ax.loglog(elog, fnonthermal2, linewidth=3)
    leg = ax.legend(
        loc=3,
        prop={'size': 20},
        ncol=1,
        shadow=False,
        fancybox=False,
        frameon=False)

    if run_name == 'mime25_beta002':
        pindex = -7.0
        sindex = 370
        pratio = 1
    elif run_name == 'mime25_beta0007':
        pindex = -5.7
        sindex = 370
        pratio = 1
    elif run_name == 'mime25_beta0001':
        pindex = -4.0
        sindex = 400
        pratio = 1

    fpower = elog[sindex:]**pindex * pratio
    ax.loglog(elog[sindex:], fpower, color='k', linestyle='--')
    ax.plot(
        elog[sindex],
        flog[sindex],
        color='k',
        marker='.',
        markersize=15,
        markevery=10,
        fillstyle='full',
        markeredgecolor='none')
    power_index = "{%0.1f}" % pindex
    tname = r'$\sim (\gamma - 1)^{' + power_index + '}$'
    ax.text(
        0.7,
        0.8,
        tname,
        color='black',
        fontsize=20,
        horizontalalignment='left',
        verticalalignment='center',
        transform=ax.transAxes)

    ax.set_xlim([2E-3, 5E1])
    ax.set_ylim([1E-8, 1E2])
    # ax.set_xlabel(r'$\gamma - 1$', fontdict=font, fontsize=24)
    ax.set_ylabel(r'$f(\gamma - 1)$', fontdict=font, fontsize=24)
    ax.tick_params(axis='x', labelbottom='off')
    ax.tick_params(labelsize=20)
    # ax.grid(True)

    h2 = 0.2
    ys -= h2 + 0.05
    ax1 = fig.add_axes([xs, ys, w1, h2])
    ax1.semilogx(elog, error_re, linewidth=2, color='k')
    xlims = ax.get_xlim()
    ax1.plot(xlims, [0.2, 0.2], linestyle='--', color='k')
    ax1.plot(xlims, [0.0, 0.0], linestyle='--', color='k')
    ax1.plot(xlims, [-0.2, -0.2], linestyle='--', color='k')
    ax1.set_xlim(xlims)
    ax1.set_ylim([-0.5, 0.5])
    ax1.tick_params(labelsize=20)
    ax1.set_xlabel(r'$\gamma - 1$', fontdict=font, fontsize=24)
    ax1.set_ylabel('Relative Error', fontdict=font, fontsize=24)
    fname = '../img/img_apj/' + 'spect_fitting_' + run_name + '.eps'
    fig.savefig(fname)

    plt.show()


def plot_contour_paths(run_name, root_dir, pic_info, ct, nlevels, ilevel):
    """plotting contours

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        ct: time frame
        nlevels: total levels of contour
        ilevel: additional contour line plot
    """
    # kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    kwargs = {"current_time": ct, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
    # fname = root_dir + "data/jy.gda"
    # x, z, jy = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + "data/Ay.gda"
    x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    nx, = x.shape
    nz, = z.shape
    width = 0.77
    height = 0.7
    xs = 0.13
    ys = 0.92 - height
    gap = 0.02
    fig = plt.figure(figsize=[8, 4])
    ax1 = fig.add_axes([xs, ys, width, height])
    kwargs_plot = {"xstep": 1, "zstep": 1, "vmin": -1.0, "vmax": 1.0}
    xstep = kwargs_plot["xstep"]
    zstep = kwargs_plot["zstep"]
    # p1, cbar1 = plot_2d_contour(x, z, jy, ax1, fig, **kwargs_plot)
    # p1.set_cmap(plt.cm.get_cmap('seismic'))
    # p1.set_cmap(cmaps.inferno)
    levels = np.linspace(np.min(Ay), np.max(Ay), nlevels)
    colors_jet = plt.cm.Paired(np.arange(nlevels) / float(nlevels), 1)

    cs = ax1.contour(
        x[0:nx:xstep],
        z[0:nz:zstep],
        Ay[0:nz:zstep, 0:nx:xstep],
        colors=colors_jet,
        linewidths=0.5,
        levels=levels)
    ax1.clabel(cs, inline=1, fontsize=16)
    ax1.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=20)
    ax1.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)
    # cbar1.set_ticks(np.arange(-0.8, 1.0, 0.4))
    # cbar1.ax.tick_params(labelsize=16)

    for cl in cs.collections[ilevel:ilevel + 1]:
        sz = len(cl.get_paths())
        for p in cl.get_paths():
            v = p.vertices
            x = v[:, 0]
            y = v[:, 1]
            ax1.plot(x, y, color='k', linewidth=2)

    xs += width + gap
    width1 = 0.03
    ax2 = fig.add_axes([xs, ys, width1, height])
    cmap = mpl.colors.ListedColormap(colors_jet)
    norm = mpl.colors.Normalize(vmin=0.5, vmax=nlevels+0.5)
    cb1 = mpl.colorbar.ColorbarBase(ax2, cmap=cmap,
            norm=norm, orientation='vertical')
    cb1.set_ticks(np.arange(1, nlevels+1, 2))
    cb1.ax.tick_params(labelsize=16)

    # plt.show()
    # plt.close()


def get_contour_paths(run_name, root_dir, pic_info, ct, nlevels, ilevel,
                      indicate_rec_layer=True, show_color_map=True):
    """Get the coordinates when plotting contours

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        ct: time frame
        nlevels: total levels of contour
        ilevel: additional contour line plot
    """
    # kwargs = {"current_time": ct, "xl": 0, "xr": 200, "zb": -50, "zt": 50}
    kwargs = {"current_time": ct, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
    # fname = root_dir + "data/jy.gda"
    # x, z, jy = read_2d_fields(pic_info, fname, **kwargs)
    fname = root_dir + "data/Ay.gda"
    x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    nx, = x.shape
    nz, = z.shape
    width = 0.77
    height = 0.7
    xs = 0.13
    ys = 0.92 - height
    gap = 0.02
    fig = plt.figure(figsize=[8, 4])
    ax1 = fig.add_axes([xs, ys, width, height])
    kwargs_plot = {"xstep": 1, "zstep": 1, "vmin": -1.0, "vmax": 1.0}
    xstep = kwargs_plot["xstep"]
    zstep = kwargs_plot["zstep"]
    # p1, cbar1 = plot_2d_contour(x, z, jy, ax1, fig, **kwargs_plot)
    # p1.set_cmap(plt.cm.get_cmap('seismic'))
    # p1.set_cmap(cmaps.inferno)
    Ay_min = np.min(Ay)
    Ay_max = np.max(Ay)
    levels = np.linspace(Ay_min, Ay_max, nlevels)
    print("Min and max of Ay: %f %f" % (Ay_min, Ay_max))
    # levels = [1, 104.5]
    levels = [1, 103]
    cs = ax1.contour(
        x[0:nx:xstep],
        z[0:nz:zstep],
        Ay[0:nz:zstep, 0:nx:xstep],
        colors='black',
        linewidths=0.5,
        levels=levels)
    ax1.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=20)
    ax1.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)
    # cbar1.set_ticks(np.arange(-0.8, 1.0, 0.4))
    # cbar1.ax.tick_params(labelsize=16)

    colors_jet = plt.cm.Paired(np.arange(nlevels) / float(nlevels), 1)
    colors_d = distinguishable_colors()
    ax1.set_color_cycle(colors_jet)
    i = 1
    fdir = 'pic_analysis/data/field_line/'
    fpath = root_dir + fdir + 't' + str(ct) + '/'
    mkdir_p(fpath)
    for cl in cs.collections:
        j = 1
        sz = len(cl.get_paths())
        for p in cl.get_paths():
            v = p.vertices
            x = v[:, 0]
            if np.all(np.diff(x) >= 0) or np.all(np.diff(x) <= 0):
                v = v[v[:, 0].argsort()]
                x = v[:, 0]
                z = v[:, 1]
                if j == 1:
                    p11, = ax1.plot(x, z, linewidth=2)
                    color = p11.get_color()
                    x1 = x
                    z1 = z
                else:
                    p11, = ax1.plot(x, z, linewidth=2, color=color)
                    xmin = np.min(x)
                    xmax = np.max(x)
                    index = (x1 >= xmin) & (x1 <= xmax)
                    x1 = x1[index]
                    z1 = z1[index]
                    f = interp1d(x, z, kind='linear')
                    z = f(x1)
                    ax1.fill_between(x1, z1, z, color=color)
                fname = 'field_line_' + str(ct) + '_' + str(i)
                if sz >= 2:
                    fname += '_' + str(j) + '.dat'
                    i += 1 if j == sz else 0
                else:
                    fname += '.dat'
                    i += 1
                v.tofile(fpath + fname)
            else:
                imin = np.argmin(x)
                imax = np.argmax(x)
                v = np.roll(v, -imin, axis=0)
                imin = np.argmin(v[:, 0])
                imax = np.argmax(v[:, 0])
                x = v[imin:imax, 0]
                z = v[imin:imax, 1]
                fname = 'field_line_' + str(ct) + '_' + str(i)
                if j == 1:
                    p1, = ax1.plot(x, z, linewidth=2)
                    color = p1.get_color()
                else:
                    p1, = ax1.plot(x, z, linewidth=2, color=color)
                if sz >= 2:
                    fname += '_' + str(j) + '_1.dat'
                else:
                    fname += '_1.dat'
                v[imin:imax, :].tofile(fpath + fname)
                x1, z1 = x, z

                v[imax:, :] = v[v[imax:, 0].argsort() + imax]
                x = v[imax:-1, 0]
                z = v[imax:-1, 1]
                ax1.plot(x, z, linewidth=2, color=color)
                fname = 'field_line_' + str(ct) + '_' + str(i)
                if sz >= 2:
                    fname += '_' + str(j) + '_2.dat'
                    i += 1 if j == sz else 0
                else:
                    fname += '_2.dat'
                    i += 1
                v[imax:-1, :].tofile(fpath + fname)
                xmin = np.min(x)
                xmax = np.max(x)
                index = (x1 >= xmin) & (x1 <= xmax)
                x1 = x1[index]
                z1 = z1[index]
                f = interp1d(x, z, kind='linear')
                z = f(x1)
                ax1.fill_between(x1, z1, z, color=color)

            j = j + 1

    if indicate_rec_layer:
        for cl in cs.collections[ilevel:ilevel + 1]:
            sz = len(cl.get_paths())
            for p in cl.get_paths():
                v = p.vertices
                x = v[:, 0]
                y = v[:, 1]
                ax1.plot(x, y, color='k', linewidth=2)

    if show_color_map:
        xs += width + gap
        width1 = 0.03
        ax2 = fig.add_axes([xs, ys, width1, height])
        cmap = mpl.colors.ListedColormap(colors_jet)
        norm = mpl.colors.Normalize(vmin=0.5, vmax=nlevels+0.5)
        cb1 = mpl.colorbar.ColorbarBase(ax2, cmap=cmap,
                norm=norm, orientation='vertical')
        cb1.set_ticks(np.arange(1, nlevels+1, 2))
        cb1.ax.tick_params(labelsize=16)

    # plt.show()
    # plt.close()


def gen_script_one_pair_field_lines(ct, ct_particle, fnames, fpath, fh,
                                    species, spect_path, vdist_path):
    """Generate script for one pair of field lines
    """
    cmd = 'particle_spectrum_vdist_fieldlines'
    script = 'mpirun -np $ncpus ' + cmd + ' -fb ' + fnames[0] + ' -ft ' + \
             fnames[1] + ' -fp ' + fpath + ' -t ' + str(ct) + \
             ' -p ' + species + '\n'
    fh.write(script)

    fname = fnames[0]
    lname = fname[10:-6]  # Remove field_line and '_1.dat' or '_2.dat'
    pre = spect_path + 'spectrum-' + species
    pre_ = spect_path + 'spectrum_' + species
    script = 'mv ' + pre + '.' + str(ct_particle) + ' ' + pre_ + '_' + \
             str(ct_particle) + lname + '.dat\n'
    fh.write(script)

    pre = vdist_path + 'vdist_1d-' + species
    pre_ = vdist_path + 'vdist_1d_' + species
    script = 'mv ' + pre + '.' + str(ct_particle) + ' ' + pre_ + '_' + \
             str(ct_particle) + lname + '.dat\n'
    fh.write(script)

    pre = vdist_path + 'vdist_2d-' + species
    pre_ = vdist_path + 'vdist_2d_' + species
    script = 'mv ' + pre + '.' + str(ct_particle) + ' ' + pre_ + '_' + \
             str(ct_particle) + lname + '.dat\n'
    fh.write(script)
    fh.write('\n')


def gen_run_script(ct, ct_particle, species, root_dir):
    """Generate run script for spectrum between field lines
    """
    fdir = 'pic_analysis/data/field_line/'
    fpath = root_dir + fdir + 't' + str(ct) + '/'
    vdist_path = root_dir + 'pic_analysis/vdistributions/'
    spect_path = root_dir + 'pic_analysis/spectrum/'
    files = [f for f in listdir(fpath) if isfile(join(fpath, f))]
    files = sorted(files)
    sz = len(files)
    fname = root_dir + 'pic_analysis/' + 'spect.sh'
    fh = open(fname, 'w')
    fh.write('#!/bin/bash\n')
    # fh.write('source module_intel.sh\n')
    fh.write('ncpus=64\n')
    for i in range(sz / 2):
        gen_script_one_pair_field_lines(ct, ct_particle,
                                        files[i * 2:i * 2 + 2], fpath, fh,
                                        species, spect_path, vdist_path)
    fh.close()
    st = os.stat(fname)
    os.chmod(fname, st.st_mode | stat.S_IEXEC)


def read_spectrum_vdist_in_sectors(ct, ct_particle, species, root_dir,
                                   pic_info):
    """Read particle spectrum and velocity distributions in sectors
    """
    fdir = 'pic_analysis/data/field_line/'
    fpath = root_dir + fdir + 't' + str(ct) + '/'
    vdist_path = root_dir + 'pic_analysis/vdistributions/'
    spect_path = root_dir + 'pic_analysis/spectrum/'
    files = [f for f in listdir(fpath) if isfile(join(fpath, f))]
    print files
    files = sorted(files)
    fnames = []
    for fname in files:
        start = [m.start() for m in re.finditer('_', fname)]
        fnames.append(fname[start[2] + 1:-6])

    sector_names = sorted(set(fnames))
    snames = {
        k: list(v)
        for k, v in groupby(
            sector_names,
            key=lambda x: x[0:x.find('_')] if x.find('_') > 0 else x)
    }
    dists_sectors = {}
    for key in snames:
        dists = []
        for fline in snames[key]:
            fname_post = species + '_' + str(ct_particle) + '_' + str(ct) + \
                         '_' + fline + '.dat'
            fname_1d = 'vdist_1d_' + fname_post
            fname_2d = 'vdist_2d_' + fname_post
            fname_ene = 'spectrum_' + fname_post
            if os.path.isfile(vdist_path + fname_1d):
                fvel = read_velocity_distribution('e', ct, pic_info, fname_1d,
                                                  fname_2d, vdist_path)
                fene = read_energy_distribution('e', ct, pic_info, fname_ene, \
                        spect_path)
                dists.append({'fvel': fvel, 'fene': fene})
        dists_sectors[key] = dists

    return dists_sectors


def compare_spectrum_in_sectors(ct, ct_particle, species, root_dir, pic_info):
    """Compare spectra in sectors with the same vector potential
    """
    dists_sector = read_spectrum_vdist_in_sectors(ct, ct_particle, species, \
                                                  root_dir, pic_info)
    fdir = 'pic_analysis/data/field_line/'
    fpath = root_dir + fdir + 't' + str(ct) + '/'
    flogs = {}
    for key in dists_sector:
        fene = []
        for dists in dists_sector[key]:
            fene.append(dists['fene'].flog)
        elog = dists['fene'].elog
        flogs[key] = fene
    clevel = 15
    nlevels = len(flogs)
    if clevel < nlevels:
        fene1 = np.asarray(flogs[str(clevel)])
        fene2 = np.asarray(flogs[str(clevel+1)])
    else:
        fene1 = np.asarray(flogs[str(clevel)])
        fene2 = np.zeros(fene1.shape)

    tframe = '30'
    fpath = root_dir + '/pic_analysis/data/field_line/t' + tframe + '/'
    width = 0.77
    height = 0.7
    xs = 0.13
    ys = 0.92 - height
    gap = 0.02
    fig = plt.figure(figsize=[8, 4])
    ax1 = fig.add_axes([xs, ys, width, height])
    line_styles = ['-', '--', '-.', ':']
    fname_pre = fpath + 'field_line_' + tframe + '_' + str(clevel)
    for i in range(len(fene1)):
        fname1 = fname_pre + '_' + str(i + 1) + '_1.dat'
        fname2 = fname_pre + '_' + str(i + 1) + '_2.dat'
        field_line1 = np.fromfile(fname1)
        field_line2 = np.fromfile(fname2)
        sz, = field_line1.shape
        field_line1 = np.reshape(field_line1, (sz/2, 2))
        sz, = field_line2.shape
        field_line2 = np.reshape(field_line2, (sz/2, 2))
        ax1.plot(field_line1[:, 0], field_line1[:, 1], linewidth=2, color='r',
                 linestyle=line_styles[i])
        ax1.plot(field_line2[:, 0], field_line2[:, 1], linewidth=2, color='r',
                 linestyle=line_styles[i])

    fname_pre = fpath + 'field_line_' + tframe + '_' + str(clevel + 1)
    if clevel < nlevels:
        for i in range(len(fene2)):
            fname1 = fname_pre + '_' + str(i + 1) + '_1.dat'
            fname2 = fname_pre + '_' + str(i + 1) + '_2.dat'
            field_line1 = np.fromfile(fname1)
            field_line2 = np.fromfile(fname2)
            sz, = field_line1.shape
            field_line1 = np.reshape(field_line1, (sz/2, 2))
            sz, = field_line2.shape
            field_line2 = np.reshape(field_line2, (sz/2, 2))
            ax1.plot(field_line1[:, 0], field_line1[:, 1], linewidth=2, color='b',
                     linestyle=line_styles[i])
            ax1.plot(field_line2[:, 0], field_line2[:, 1], linewidth=2, color='b',
                     linestyle=line_styles[i])

    ax1.set_ylim([-20, 20])
    ax1.set_xlabel(r'$x/d_i$', fontdict=font, fontsize=20)
    ax1.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
    ax1.tick_params(labelsize=16)
    

    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    fsec = fene1 - fene2
    fsec1 = fsec[0] + fsec[1]
    fsec2 = fsec[2]
    # fsec1 = fsec[0]
    # fsec2 = fsec[1]
    nacc1, eacc1 = accumulated_particle_info(elog, fsec1)
    nacc2, eacc2 = accumulated_particle_info(elog, fsec2)
    nratio = nacc1[-1] / nacc2[-1]
    ax.loglog(elog, fsec1, linewidth=2)
    ax.loglog(elog, fsec2 * nratio, linewidth=2)
    ax.set_xlabel(r'$\gamma - 1$', fontdict=font, fontsize=24)
    ax.set_ylabel(r'$f(\gamma - 1)$', fontdict=font, fontsize=24)
    ax.tick_params(labelsize=16)
    plt.show()


def plot_spectrum_in_sectors(ct, ct_particle, species, root_dir, pic_info,
                             run_name, nlevels, ilevel):
    """Plot particle spectrum and velocity distributions in sectors
    """
    dists_sector = read_spectrum_vdist_in_sectors(ct, ct_particle, species, \
                                                  root_dir, pic_info)
    flogs = {}
    for key in dists_sector:
        fene = []
        for dists in dists_sector[key]:
            fene.append(dists['fene'].flog)
        elog = dists['fene'].elog
        fene = np.sum(np.asarray(fene), axis=0)
        flogs[key] = fene
        # flog = np.asarray(fene)
        # flogs[key] = flog[-1]

    # fig = plt.figure(figsize=[7, 5])
    # xs, ys = 0.15, 0.15
    # w1, h1 = 0.8, 0.8
    fig = plt.figure(figsize=[5, 5])
    xs, ys = 0.21, 0.15
    w1, h1 = 0.75, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    colors_jet = plt.cm.Paired(np.arange(nlevels) / float(nlevels), 1)
    colors_d = distinguishable_colors()

    start_level = 1
    ax.set_prop_cycle(cycler('color', colors_jet[start_level-1:]))
    nsector = len(flogs)
    norm = 1
    nacc_max = 0
    for i in range(start_level, nsector):
        f = (flogs[str(i)] - flogs[str(i + 1)]) * norm
        nacc1, eacc1 = accumulated_particle_info(elog, f)
        nacc_max = max(nacc1[-1], nacc_max)
    for i in range(start_level, nsector, 2):
        f = (flogs[str(i)] - flogs[str(i + 1)]) * norm
        nacc1, eacc1 = accumulated_particle_info(elog, f)
        # ax.loglog(elog, f * nacc_max / nacc1[-1], linewidth=3, color=colors_jet[i-1])
        ax.loglog(elog, f, linewidth=3, color=colors_jet[i-1])
        fthermal1, popt = fit_thermal_core(elog, f)
        ax.loglog(elog, fthermal1, linewidth=1, color='k', linestyle='--')
        print("sector %d peaks at %f" % (i, elog[np.argmax(fthermal1)]))
        print colors_jet[i-1]
    flog = flogs[str(nsector)] * norm
    nacc1, eacc1 = accumulated_particle_info(elog, flog)
    # flog *= nacc_max / nacc1[-1]
    # flog = flogs[str(nsector-1)] - flogs[str(nsector)]
    fthermal1, popt = fit_thermal_core(elog, flog)
    fnonthermal1 = flog - fthermal1
    imax = np.argmax(fnonthermal1)
    ns = imax + 20
    fthermal2, popt = fit_thermal_core(elog[ns:], fnonthermal1[ns:])
    fthermal2 = fitting_funcs.func_maxwellian(elog, popt[0], popt[1])
    fnonthermal2 = fnonthermal1 - fthermal2
    pindex = -5.5
    fpower = elog**pindex
    fpower *= flog[ns] / fpower[ns]
    fpower *= 1E3
    powerIndex = "{%0.2f}" % pindex
    pname = '$\sim (\gamma - 1)^{' + powerIndex + '}$'
    ax.loglog(elog, flog, linewidth=3, color=colors_jet[nsector-1])
    ax.loglog(elog, fthermal1, linewidth=1, color='k', linestyle='--')
    print("sector %d peaks at %f" % (i+1, elog[np.argmax(fthermal1)]))
    # ax.loglog(elog, flogs[str(ilevel)], linewidth=3,
    #     color='k', label='Reconnection region')
    # # ax.loglog(elog[ns:], fpower[ns:], linewidth=2, linestyle='--',
    # #         color='k', label=pname)
    # # ax.loglog(
    # #     elog,
    # #     fthermal1,
    # #     color='k',
    # #     linestyle='--',
    # #     linewidth=2,
    # #     label='Fitted Maxwellian')
    # # ax.loglog(elog, fnonthermal1, color='k', linestyle='-', linewidth=2)
    # # ax.loglog(elog, fthermal2, color='k', linestyle='--', linewidth=2)
    # # ax.loglog(elog, fnonthermal2, color='k', linestyle='--', linewidth=2)
    # leg = ax.legend( loc=3, prop={'size': 16}, ncol=1,
    #         shadow=False, fancybox=False, frameon=False)
    ax.xaxis.grid()
    ax.tick_params(labelsize=20)
    ax.set_xlabel(r'$\gamma - 1$', fontdict=font, fontsize=24)
    ax.set_ylabel(r'$f(\gamma - 1)$', fontdict=font, fontsize=24)
    if run_name == 'mime25_beta02':
        if species == 'e':
            ax.set_xlim([1E-3, 1E0])
            ax.set_ylim([1E-5, 2E5])
        else:
            ax.set_xlim([1E-4, 1E0])
            ax.set_ylim([1E-4, 5E6])
    elif run_name == 'mime25_beta002':
        if species == 'e':
            ax.set_xlim([1E-3, 1E1])
            ax.set_ylim([1E-5, 1E5])
        else:
            ax.set_xlim([1E-4, 1E0])
            ax.set_ylim([1E-4, 5E6])
    elif run_name == 'mime25_beta0007':
        if species == 'e':
            ax.set_xlim([1E-4, 3E1])
            ax.set_ylim([1E-5, 1E5])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 5E6])
    elif run_name == 'mime25_beta0002':
        if species == 'e':
            ax.set_xlim([1E-4, 3E2])
            ax.set_ylim([1E-6, 2E4])
        else:
            ax.set_xlim([1E-4, 1E1])
            ax.set_ylim([1E-4, 1E6])
    elif run_name == 'mime25_sigma30':
        if species == 'e':
            ax.set_xlim([1E-4, 2E3])
            ax.set_ylim([1E-5, 1E6])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])
    elif run_name == 'mime25_sigma100':
        if species == 'e':
            ax.set_xlim([1E-4, 2E3])
            ax.set_ylim([1E-5, 5E5])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])
    elif run_name == 'mime25_beta0001':
        if species == 'e':
            ax.set_xlim([1E-4, 1E2])
            ax.set_ylim([1E-5, 5E5])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])
    elif run_name == 'sigma1-mime25-beta0002-fan':
        if species == 'e':
            ax.set_xlim([1E-4, 1E1])
            ax.set_ylim([1E-4, 1E7])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])
    elif run_name == 'sigma100-lx300':
        if species == 'e':
            ax.set_xlim([1E-2, 1E3])
            ax.set_ylim([1E-4, 1E4])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])
    else:
        if species == 'e':
            ax.set_xlim([1E-3, 2E0])
            ax.set_ylim([1E-2, 1E6])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])

    # fig = plt.figure(figsize=[7, 5])
    # xs, ys = 0.15, 0.15
    # w1, h1 = 0.8, 0.8
    # ax = fig.add_axes([xs, ys, w1, h1])
    # colors_jet = plt.cm.jet(np.arange(nlevels)/float(nlevels), 1)
    # ax.set_color_cycle(colors_jet)
    # for i in range(nsector-1):
    #     ntot, etot = accumulated_particle_info(elog,
    #             flogs[str(i+1)] - flogs[str(i+2)])
    #     ax.semilogx(elog, ntot, linewidth=2)
    # ntot, etot = accumulated_particle_info(elog, flog)
    # ax.semilogx(elog, ntot, linewidth=2)
    # ax.xaxis.grid()
    # ax.tick_params(labelsize=20)
    # ax.set_xlabel(r'$\gamma - 1$', fontdict=font, fontsize=24)

    # plt.show()


def plot_vdist_in_sectors(ct, ct_particle, species, root_dir, pic_info,
                             run_name, nlevels, ilevel):
    """Plot velocity distributions in sectors
    """
    dists_sector = read_spectrum_vdist_in_sectors(ct, ct_particle, species, \
                                                  root_dir, pic_info)
    fvels_xy = {}
    fvels_xz = {}
    fvels_yz = {}
    for key in dists_sector:
        fvel_xy = []
        fvel_xz = []
        fvel_yz = []
        for dists in dists_sector[key]:
            fvel_xy.append(dists['fvel'].fvel_xy)
            fvel_xz.append(dists['fvel'].fvel_xz)
            fvel_yz.append(dists['fvel'].fvel_yz)
        vbins = dists['fvel'].vbins_long
        fvel_xy = np.asarray(fvel_xy)
        fvel_xz = np.asarray(fvel_xz)
        fvel_yz = np.asarray(fvel_yz)
        fvel_xy = np.sum(np.asarray(fvel_xy), axis=0)
        fvel_xz = np.sum(np.asarray(fvel_xz), axis=0)
        fvel_yz = np.sum(np.asarray(fvel_yz), axis=0)
        fvels_xy[key] = fvel_xy
        fvels_xz[key] = fvel_xz
        fvels_yz[key] = fvel_yz

    umin = np.min(vbins)
    umax = np.max(vbins)

    fux1 = {}
    fuy1 = {}
    fuz1 = {}
    fux2 = {}
    fuy2 = {}
    fuz2 = {}
    for key in fvels_xy:
        fux1[key] = np.sum(fvels_xy[key], axis=0)
        fuy1[key] = np.sum(fvels_xy[key], axis=1)
        fuz1[key] = np.sum(fvels_yz[key], axis=1)
        # fuy2[key] = np.sum(fvels_yz[key], axis=0)
        # fux2[key] = np.sum(fvels_xz[key], axis=0)
        # fuz2[key] = np.sum(fvels_xz[key], axis=1)

    nsectors = len(fux1)
    fig = plt.figure(figsize=[20, 5])
    xs0, ys0 = 0.05, 0.15
    w1, h1 = 0.28, 0.8
    gap = 0.05
    xs1 = xs0 + w1 + gap
    xs2 = xs1 + w1 + gap
    ax1 = fig.add_axes([xs0, ys0, w1, h1])
    ax2 = fig.add_axes([xs1, ys0, w1, h1])
    ax3 = fig.add_axes([xs2, ys0, w1, h1])
    colors_jet = plt.cm.jet(np.arange(nsectors) / float(nsectors), 1)
    ax1.set_color_cycle(colors_jet)
    ax2.set_color_cycle(colors_jet)
    ax3.set_color_cycle(colors_jet)
    for i in range(nsectors - 1):
        key1 = str(i + 1)
        key2 = str(i + 2)
        fux_sec = fux1[key1] - fux1[key2]
        fuy_sec = fuy1[key1] - fuy1[key2]
        fuz_sec = fuz1[key1] - fuz1[key2]
        ax1.semilogy(vbins, fux_sec/np.sum(fux_sec), linewidth=2)
        ax2.semilogy(vbins, fuy_sec/np.sum(fuy_sec), linewidth=2)
        ax3.semilogy(vbins, fuz_sec/np.sum(fuz_sec), linewidth=2)
        print np.sum(fuy_sec)
    key = str(nsectors)
    ax1.semilogy(vbins, fux1[key]/np.sum(fux1[key]), linewidth=2)
    ax2.semilogy(vbins, fuy1[key]/np.sum(fuy1[key]), linewidth=2)
    ax3.semilogy(vbins, fuz1[key]/np.sum(fuz1[key]), linewidth=2)
    ax2.set_ylim(ax1.get_ylim())
    ax3.set_ylim(ax1.get_ylim())
    # ax1.set_xlim([-0.5, 0.5])
    # ax2.set_xlim(ax1.get_xlim())
    # ax3.set_xlim(ax1.get_xlim())
    ax1.plot([0, 0], ax1.get_ylim(), color='k', linestyle='--')
    ax2.plot([0, 0], ax2.get_ylim(), color='k', linestyle='--')
    ax3.plot([0, 0], ax3.get_ylim(), color='k', linestyle='--')
    ax1.tick_params(labelsize=16)
    ax2.tick_params(labelsize=16)
    ax3.tick_params(labelsize=16)
    ax1.set_xlabel(r'$u_x$', fontsize=20)
    ax2.set_xlabel(r'$u_y$', fontsize=20)
    ax3.set_xlabel(r'$u_z$', fontsize=20)
    ax1.set_ylabel(r'$f(u_x)$', fontsize=20)
    ax2.set_ylabel(r'$f(u_y)$', fontsize=20)
    ax3.set_ylabel(r'$f(u_z)$', fontsize=20)

    fpath = '../img/canonical_p/' + run_name + '/'
    mkdir_p(fpath)
    fig.savefig(fpath + 'fux_fuy_fuz.eps')
    plt.show()

    # fig = plt.figure(figsize=[8, 8])
    # xs0, ys0 = 0.12, 0.1
    # w1, h1 = 0.85, 0.85
    # ax1 = fig.add_axes([xs0, ys0, w1, h1])
    # vmin = 1.0
    # vmax = 3.0E6
    # p1 = ax1.imshow(fvels_xy['11'], cmap=plt.cm.viridis,
    #     extent=[umin, umax, umin, umax], aspect='auto', origin='lower',
    #     norm = LogNorm(vmin=vmin, vmax=vmax), interpolation='bicubic')
    # ax1.set_xlabel(r'$u_x$', fontsize=20)
    # ax1.set_ylabel(r'$u_y$', fontsize=20)
    # ax1.tick_params(labelsize=16)
    # plt.show()


def fit_spectrum_reconnection_region(ct, ct_particle, species, root_dir,
        pic_info, run_name, nlevels, ilevel):
    """Plot particle spectrum and velocity distributions in sectors
    """
    dists_sector = read_spectrum_vdist_in_sectors(ct, ct_particle, species, \
                                                  root_dir, pic_info)
    flogs = {}
    for key in dists_sector:
        fene = []
        for dists in dists_sector[key]:
            fene.append(dists['fene'].flog)
        elog = dists['fene'].elog
        fene = np.sum(np.asarray(fene), axis=0)
        flogs[key] = fene

    fig = plt.figure(figsize=[10, 10])
    xs, ys = 0.12, 0.1
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    colors_jet = plt.cm.Paired(np.arange(nlevels) / float(nlevels), 1)
    colors_d = distinguishable_colors()

    flog = flogs[str(ilevel)]

    fthermal1, popt = fit_thermal_core(elog, flog)
    fnonthermal1 = flog - fthermal1
    imax = np.argmax(fnonthermal1)
    ns = imax + 20
    fthermal2, popt = fit_thermal_core(elog[ns:], fnonthermal1[ns:])
    fthermal2 = fitting_funcs.func_maxwellian(elog, popt[0], popt[1])
    fnonthermal2 = fnonthermal1 - fthermal2

    imax = np.argmax(fnonthermal2)
    ns = imax + 20
    fthermal3, popt = fit_thermal_core(elog[ns:], fnonthermal2[ns:])
    fthermal3 = fitting_funcs.func_maxwellian(elog, popt[0], popt[1])
    fnonthermal3 = fnonthermal2 - fthermal3

    imax = np.argmax(fnonthermal3)
    ns = imax + 20
    fthermal4, popt = fit_thermal_core(elog[ns:], fnonthermal3[ns:])
    fthermal4 = fitting_funcs.func_maxwellian(elog, popt[0], popt[1])
    fnonthermal4 = fnonthermal3 - fthermal4

    ax.loglog(elog, flog, linewidth=3, color='k', label='Reconnection region')
    # ax.loglog(elog, flog, linewidth=3, color='k', linestyle='',
    #         marker='o', markersize=1, label='Reconnection region')
    ax.loglog(elog, fthermal1, color='r', linestyle='--', linewidth=2)
    ax.loglog(elog, fnonthermal1, color='r', linestyle='-', linewidth=2)
    ax.loglog(elog, fthermal2, color='g', linestyle='--', linewidth=2)
    ax.loglog(elog, fnonthermal2, color='g', linestyle='-', linewidth=2)
    ax.loglog(elog, fthermal3, color='b', linestyle='--', linewidth=2)
    ax.loglog(elog, fnonthermal3, color='b', linestyle='-', linewidth=2)
    ax.loglog(elog, fthermal4, color='m', linestyle='--', linewidth=2)
    ax.loglog(elog, fnonthermal4, color='m', linestyle='-', linewidth=2)

    flog_fitted = fthermal1 + fthermal2 + fthermal3 + fthermal4

    # ax.loglog(elog, flog_fitted, linewidth=3, color='k', linestyle='--',
    #         label='Reconnection region')

    ax.xaxis.grid()
    ax.tick_params(labelsize=20)
    ax.set_xlabel(r'$\gamma - 1$', fontdict=font, fontsize=24)
    ax.set_ylabel(r'$f(\gamma - 1)$', fontdict=font, fontsize=24)
    if run_name == 'sigma1-mime25-beta0002-fan':
        if species == 'e':
            ax.set_xlim([1E-4, 1E1])
            ax.set_ylim([1E-4, 0.1E7])
        else:
            ax.set_xlim([1E-4, 3E0])
            ax.set_ylim([1E-4, 1E6])



def plot_velocity_fields(run_name, root_dir, pic_info, species):
    """Plot magnetic fields

    Args:
        run_name: the name of this run.
        root_dir: the root directory of this run.
        pic_info: PIC simulation information in a namedtuple.
        species: particle species.
    """
    ct = 100
    contour_color = ['k', 'k', 'k']
    vmin = [-1.0, -1.0, -1.0]
    vmax = [1.0, 1.0, 1.0]
    xs, ys = 0.15, 0.77
    w1, h1 = 0.7, 0.21
    axis_pos = [xs, ys, w1, h1]
    gaps = [0.1, 0.025]
    fig_sizes = (6, 10)
    nxp, nzp = 1, 3
    var_names = []
    var_name = r'$V_{' + species + 'x}/V_A$'
    var_names.append(var_name)
    var_name = r'$V_{' + species + 'y}/V_A$'
    var_names.append(var_name)
    var_name = r'$V_{' + species + 'z}/V_A$'
    var_names.append(var_name)
    colormaps = ['seismic', 'seismic', 'seismic']
    text_colors = colors[:3]
    xstep, zstep = 2, 2
    is_logs = [False, False, False]
    wpe_wce = pic_info.dtwce / pic_info.dtwpe
    va = wpe_wce / math.sqrt(pic_info.mime)  # Alfven speed of inflow region
    fig_dir = '../img/img_apj/' + run_name + '/'
    mkdir_p(fig_dir)
    kwargs = {"current_time": ct, "xl": 100, "xr": 120, "zb": -20, "zt": 20}
    fname2 = root_dir + 'data/v' + species + 'x.gda'
    if os.path.isfile(fname2):
        fname3 = root_dir + 'data/v' + species + 'y.gda'
        fname4 = root_dir + 'data/v' + species + 'z.gda'
    else:
        fname2 = root_dir + 'data/u' + species + 'x.gda'
        fname3 = root_dir + 'data/u' + species + 'y.gda'
        fname4 = root_dir + 'data/u' + species + 'z.gda'
    x, z, vx = read_2d_fields(pic_info, fname2, **kwargs)
    x, z, vy = read_2d_fields(pic_info, fname3, **kwargs)
    x, z, vz = read_2d_fields(pic_info, fname4, **kwargs)
    fname5 = root_dir + 'data/Ay.gda'
    x, z, Ay = read_2d_fields(pic_info, fname5, **kwargs)
    nz, nx = vx.shape
    fdata = [vx / va, vy / va, vz / va]
    fdata_1d = [vx[nz / 2, :] / va, vy[nz / 2, :] / va, vz[nz / 2, :] / va]
    fname = 'v' + species
    bottom_panel = True
    kwargs_plots = {
        'current_time': ct,
        'x': x,
        'z': z,
        'Ay': Ay,
        'fdata': fdata,
        'contour_color': contour_color,
        'colormaps': colormaps,
        'vmin': vmin,
        'vmax': vmax,
        'var_names': var_names,
        'axis_pos': axis_pos,
        'gaps': gaps,
        'fig_sizes': fig_sizes,
        'text_colors': text_colors,
        'nxp': nxp,
        'nzp': nzp,
        'xstep': xstep,
        'zstep': zstep,
        'is_logs': is_logs,
        'fname': fname,
        'fig_dir': fig_dir,
        'bottom_panel': bottom_panel,
        'fdata_1d': fdata_1d
    }
    vfields_plot = PlotMultiplePanels(**kwargs_plots)

    plt.show()


def get_ay_distribution(run_name, root_dir, pic_info):
    """Get Ay distribution
    """
    kwargs = {"current_time": 0, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
    fname = root_dir + "data/Ay.gda"
    x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
    ay_min = np.min(Ay)
    ay_max = np.max(Ay)
    nbins = 100
    ay_bins = np.linspace(ay_min, ay_max, nbins)
    hist_ay1, bin_edges = np.histogram(Ay, bins=ay_bins, density=True)
    print np.max(Ay)

    ntf = pic_info.ntf
    t_interval = 10
    nt = ntf / t_interval + 1

    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])

    colors_jet = plt.cm.jet(np.arange(nt) / float(nt), 1)
    ax.set_color_cycle(colors_jet)

    ax.plot(bin_edges[:-1], hist_ay1, linewidth=2, label=r'$t=0$')

    for ct in range(t_interval, ntf, t_interval):
        kwargs = {"current_time": ct, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
        x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
        hist_ay2, bin_edges = np.histogram(Ay, bins=ay_bins, density=True)
        ax.plot(bin_edges[:-1], hist_ay2, linewidth=2, label=r'$t=$last')
        print np.max(Ay)


    # leg = ax.legend(loc=3, prop={'size': 20}, ncol=1,
    #     shadow=False, fancybox=False, frameon=False)

    ax.set_xlabel(r'$A_y$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$f(A_y)$', fontdict=font, fontsize=20)
    ax.tick_params(labelsize=16)

    fpath = '../img/canonical_p/' + run_name + '/'
    mkdir_p(fpath)
    fig.savefig(fpath + 'fAy_time.eps')

    plt.show()


def ay_at_boundary(run_name, root_dir, pic_info):
    """Get Ay at the boundary
    """
    kwargs = {"current_time": 0, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
    fname = root_dir + "data/Ay.gda"
    x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
    nx, = x.shape
    nz, = z.shape
    ay_min = np.min(Ay)
    ay_max = np.max(Ay)
    nbins = 100
    ay_bins = np.linspace(ay_min, ay_max, nbins)
    ix = 7 * nx / 8
    ay1 = Ay[:, ix]

    ntf = pic_info.ntf
    t_interval = 40
    nt = ntf / t_interval + 1

    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])

    colors_jet = plt.cm.jet(np.arange(nt) / float(nt), 1)
    ax.set_color_cycle(colors_jet)

    ax.plot(z, ay1, linewidth=2, label=r'$t=0$')

    for ct in range(t_interval, ntf, t_interval):
        kwargs = {"current_time": ct, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
        x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
        ay2 = Ay[:, ix]
        ax.plot(z, ay2, linewidth=2, label=r'$t=$last')


    ax.set_xlabel(r'$z$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$A_y$', fontdict=font, fontsize=20)
    ax.tick_params(labelsize=16)

    fpath = '../img/canonical_p/' + run_name + '/'
    mkdir_p(fpath)
    fig.savefig(fpath + 'Ay_z.eps')

    plt.show()


def spectrum_between_fieldlines():
    """Analysis for particle spectrum between field lines
    """
    species = 'e'
    # run_name = "mime25_beta02"
    # root_dir = "/net/scratch2/xiaocanli/mime25-sigma01-beta02-200-100/"
    # run_name = "mime25_beta002"
    # root_dir = "/net/scratch2/guofan/sigma1-mime25-beta001/"
    # run_name = "mime25_beta0007"
    # root_dir = '/net/scratch2/xiaocanli/mime25-guide0-beta0007-200-100/'
    # run_name = "mime25_beta0002"
    # root_dir = "/net/scratch3/xiaocanli/mime25-sigma1-beta0002/"
    # run_name = "mime25_beta002_track"
    # root_dir = '/net/scratch2/guofan/sigma1-mime25-beta001-track-3/'
    # run_name = "mime25_sigma30"
    # root_dir = '/net/scratch3/xiaocanli/mime25-sigma30-200-100/'
    # run_name = "mime25_sigma100"
    # root_dir = '/net/scratch3/xiaocanli/mime25-sigma100-200-100/'
    # run_name = "mime25_beta0001"
    # root_dir = "/net/scratch2/guofan/sigma1-mime25-beta0001/"
    # run_name = 'sigma1-mime25-beta0002-fan'
    # root_dir = '/net/scratch1/guofan/Project2017/low-beta/sigma1-mime25-beta0002/'
    # run_name = 'sigma100-lx300'
    # root_dir = '/net/scratch2/guofan/for_Xiaocan/sigma100-lx300/'
    run_name = 'Lx164-nuwce0.04-betabol0.08-L2di-nx3072-150nppc-dumppart'
    root_dir = '/net/scratch3/stanier/VPIC-collisions-test/FF-coll-plasmoid/' + run_name + '/'
    picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    # ct_particle = pic_info.ntp
    ct_particle = 4
    ct = ct_particle * pic_info.particle_interval / pic_info.fields_interval
    nlevels = 20
    indicate_rec_layer = True
    show_color_map = True
    fpath = '../img/spect_vdist_fieldlines/' + run_name
    if run_name == 'mime25_beta02':
        ilevel = 8
    elif run_name == 'mime25_beta002':
        ilevel = 6
    elif run_name == 'mime25_beta0007':
        ilevel = 5
    elif run_name == 'mime25_beta0001':
        ilevel = 6
    elif run_name == 'sigma1-mime25-beta0002-fan':
        ilevel = 10
    elif run_name == 'Lx164-nuwce0.04-betabol0.08-L2di-nx3072-150nppc-dumppart':
        nlevels = 2
        ilevel = 1
        root_dir = '/net/scratch3/xiaocanli/reconnection/NERSC_ADAM/'
        indicate_rec_layer = False
        show_color_map = False
    get_contour_paths(run_name, root_dir, pic_info, ct, nlevels, ilevel,
                      indicate_rec_layer, show_color_map)
    mkdir_p(fpath)
    fname = fpath + '/contour_' + str(ct) + '.jpg'
    plt.savefig(fname, dpi=300)
    # for tframe in range(ct+1):
    #     plot_contour_paths(run_name, root_dir, pic_info, tframe, nlevels, ilevel)
    #     fname = fpath + '/contour_label_' + str(ct) + '.jpg'
    #     plt.savefig(fname, dpi=300)
    #     plt.close()
    # gen_run_script(ct, ct_particle, species, root_dir)
    plot_spectrum_in_sectors(ct, ct_particle, species, root_dir, pic_info,
                             run_name, nlevels, ilevel)
    # plot_vdist_in_sectors(ct, ct_particle, species, root_dir, pic_info,
    #                          run_name, nlevels, ilevel)
    # fname = fpath + '/spect_sector_' + species + '_' + str(ct) + '.eps'
    # plt.savefig(fname)
    # fit_spectrum_reconnection_region(ct, ct_particle, species, root_dir,
    #         pic_info, run_name, nlevels, ilevel)
    plt.show()
    # compare_spectrum_in_sectors(ct, ct_particle, species, root_dir, pic_info)
    # get_ay_distribution(run_name, root_dir, pic_info)
    # ay_at_boundary(run_name, root_dir, pic_info)


def calc_canonical_p(mpi_rank, fbase, smime, Ay, fpath, f):
    """Calculate canonical momentum for a single MPI rank

    Args:
        mpi_rank: MPI rank for PIC simulation
        fbase: the particle data file base
        smime: square root of proton-electron mass ratio
        Ay: the y-component of the vector potential
        fpath: the output file path
        f: interpolation function
    """
    print mpi_rank
    fname = fbase + str(mpi_rank)
    (v0, pheader, ptl) = read_particle_data(fname)
    dx = ptl['dxyz'][:, 0]
    dz = ptl['dxyz'][:, 2]
    icell = ptl['icell']
    nx = v0.nx + 2
    ny = v0.ny + 2
    nz = v0.nz + 2
    iz = icell // (nx * ny)
    iy = (icell - iz * nx * ny) // nx
    ix = icell - iz * nx * ny - iy * nx
    x_ptl = v0.x0 + ((ix - 1.0) + (dx + 1.0) * 0.5) * v0.dx
    z_ptl = v0.z0 + ((iz - 1.0) + (dz + 1.0) * 0.5) * v0.dz
    # de -> di
    x_ptl /= smime
    z_ptl /= smime
    nptl, = x_ptl.shape
    canonical_py = 0.0
    Ay_ptl = f(x_ptl, z_ptl, grid=False)

    py_tot = np.sum(ptl['u'][:, 1])
    Ay_ptl_tot = np.sum(-Ay_ptl)

    fname = fpath + 'mpi_rank_' + str(mpi_rank) + '.dat'
    data = np.asarray([nptl, py_tot, Ay_ptl_tot])
    data.tofile(fname)


def combine_canonical_p_files(ct_particle, run_name, mpi_size):
    """combine canonical momentum files and average the data
    """
    fpath = '../data/canonical_p/' + run_name + '/t' + str(ct_particle) + '/'
    py_tot = 0.0
    ay_tot = 0.0
    ntot = 0
    for i in range(mpi_size):
        fname = fpath + 'mpi_rank_' + str(i) + '.dat'
        data = np.fromfile(fname)
        ntot += data[0]
        py_tot += data[1] 
        ay_tot += data[2] 

    return (py_tot / ntot, ay_tot / ntot)


def calc_canonical_momentum():
    """Calculate canonical momentum of the system
    """
    run_name = 'sigma100-lx300'
    root_dir = '/net/scratch2/guofan/for_Xiaocan/sigma100-lx300/'
    # run_name = "mime25_beta002"
    # root_dir = "/net/scratch2/guofan/sigma1-mime25-beta001/"
    picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    tx = pic_info.topology_x
    ty = pic_info.topology_y
    tz = pic_info.topology_z
    smime = math.sqrt(pic_info.mime)
    ntp = pic_info.ntp
    ct_particle = 1
    # plot_energy_evolution(pic_info)

    num_cores = multiprocessing.cpu_count()
    mpi_size = tx * ty * tz
    mpi_ranks = range(mpi_size)
    canonical_py = np.zeros((pic_info.ntp, 2))
    for ct_particle in range(1, pic_info.ntp + 1):
        print ct_particle
        data = combine_canonical_p_files(ct_particle, run_name, mpi_size)
        canonical_py[ct_particle-1, 0] = data[0]
        canonical_py[ct_particle-1, 1] = data[1]
        continue
        particle_interval = pic_info.particle_interval
        tindex = ct_particle * particle_interval
        ct = ct_particle * particle_interval / pic_info.fields_interval

        kwargs = {"current_time": ct, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
        fname = root_dir + "data2/Ay.gda"
        x, z, Ay = read_2d_fields(pic_info, fname, **kwargs)
        x = np.linspace(0, pic_info.lx_di, pic_info.nx)
        z = np.linspace(-pic_info.lz_di*0.5, pic_info.lz_di*0.5, pic_info.nz)
        f = interpolate.interp2d(x, z, Ay, kind='linear')
        spl = RectBivariateSpline(x, z, Ay.T)

        dir_name = root_dir + 'particle/T.' + str(tindex) + '/'
        fbase = dir_name + 'hparticle' + '.' + str(tindex) + '.'

        fpath = '../data/canonical_p/' + run_name + '/t' + str(ct_particle) + '/'
        mkdir_p(fpath)

        # calc_canonical_p(0, fbase, smime, Ay, fpath, spl)
        Parallel(n_jobs=num_cores)(delayed(calc_canonical_p)(mpi_rank, fbase, smime, Ay, fpath, spl)
                for mpi_rank in mpi_ranks)

    dpy = canonical_py[-1, 0] - canonical_py[0, 0]
    day = canonical_py[-1, 1] - canonical_py[0, 1]
    cpy = canonical_py[:, 0] - canonical_py[:, 1] * abs(dpy / day)
    print abs(dpy / day)

    t = np.arange(ntp) * pic_info.dt_particles
    fig = plt.figure(figsize=[7, 5])
    xs, ys = 0.15, 0.15
    w1, h1 = 0.8, 0.8
    ax = fig.add_axes([xs, ys, w1, h1])
    ax.plot(t, (cpy - cpy[0]) / cpy[0], linewidth=2)
    ax.set_xlabel(r'$t\Omega_{ci}$', fontdict=font, fontsize=20)
    ax.set_ylabel(r'$p_y$', fontdict=font, fontsize=20)
    ax.tick_params(labelsize=16)
    fpath = '../img/canonical_p/' + run_name + '/'
    mkdir_p(fpath)
    # fig.savefig(fpath + 'canonical_py.eps')
    plt.show()


if __name__ == "__main__":
    cmdargs = sys.argv
    if (len(cmdargs) > 2):
        base_dir = cmdargs[1]
        run_name = cmdargs[2]
    else:
        base_dir = '/net/scratch2/guofan/sigma1-mime25-beta001-average/'
        run_name = 'sigma1-mime25-beta001-average'
    # scratch_dir = '/net/scratch2/xiaocanli/'
    # run_name = "mime25_beta002_noperturb"
    # root_dir = scratch_dir + 'mime25-sigma1-beta002-200-100-noperturb/'
    # run_name = "mime25_beta002"
    # root_dir = "/net/scratch2/xiaocanli/sigma1-mime25-beta001/"
    # run_name = "mime25_beta0002"
    # root_dir = "/net/scratch3/xiaocanli/sigma1-mime25-beta0002/"
    # run_name = "mime25_beta0007"
    # root_dir = '/net/scratch2/xiaocanli/mime25-guide0-beta0007-200-100/'
    # run_name = "mime25_beta002_track"
    # root_dir = '/net/scratch2/guofan/sigma1-mime25-beta001-track-3/'
    # run_name = 'sigma1-mime25-beta0002-fan'
    # root_dir = '/net/scratch1/guofan/Project2017/low-beta/sigma1-mime25-beta0002/'
    picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    # plot_by_time(run_name, root_dir, pic_info)
    # plot_absB_time(run_name, root_dir, pic_info)
    # plot_absB(run_name, root_dir, pic_info, 62)
    # plot_agyrotropy(run_name, root_dir, pic_info, 'e', 62)
    # plot_vx_time(run_name, root_dir, pic_info)
    # plot_epara_eperp(pic_info, 26, root_dir)
    # plot_epara_eperp(pic_info, 61, root_dir)
    # plot_jpara_dote(run_name, root_dir, pic_info, 'i')
    # plot_jdrifts_dote_fields()
    # plot_jdotes_multi(run_name, root_dir, pic_info)
    # plot_uxyz_multi(run_name, root_dir, pic_info)
    # plot_epara_xyz_multi(run_name, root_dir, pic_info)
    # plot_eperp_xyz_multi(run_name, root_dir, pic_info)
    # plot_emfields_multi(run_name, root_dir, pic_info)
    # plot_gradB_multi(run_name, root_dir, pic_info)
    # plot_ppara_pperp_multi(run_name, root_dir, pic_info)
    # plot_curvb_multi(run_name, root_dir, pic_info)
    # plot_spectra_electron()
    # plot_spectra_R1_R5()
    # fit_two_maxwellian()
    spectrum_between_fieldlines()
    # plot_velocity_fields(run_name, root_dir, pic_info, 'e')
    # calc_canonical_momentum()
