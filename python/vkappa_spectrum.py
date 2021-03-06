"""
#!/usr/bin/env python3
"""
from __future__ import print_function

import argparse
import itertools
import json
import multiprocessing

import h5py
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from joblib import Parallel, delayed
from matplotlib.colors import LogNorm

import pic_information
from json_functions import read_data_from_json
from shell_functions import mkdir_p

mpl.rc('text', usetex=True)
mpl.rcParams['text.latex.preamble'] = [r"\usepackage{amsmath}"]

def plot_spectrum(plot_config, show_plot=True):
    """Plot power spectrum

    Args:
        plot_config: plot configuration
    """
    pic_run = plot_config["pic_run"]
    pic_run_dir = plot_config["pic_run_dir"]
    tframe = plot_config["tframe"]
    var_name = plot_config["var_name"]
    picinfo_fname = '../data/pic_info/pic_info_' + pic_run + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    tratio = pic_info.particle_interval / pic_info.fields_interval
    tindex = tframe * pic_info.fields_interval
    fname = pic_run_dir + "vkappa_spectrum/" + var_name + str(tindex) + ".kx"
    fx = np.fromfile(fname, dtype=np.float32)
    fname = pic_run_dir + "vkappa_spectrum/" + var_name + str(tindex) + ".ky"
    fy = np.fromfile(fname, dtype=np.float32)
    fname = pic_run_dir + "vkappa_spectrum/" + var_name + str(tindex) + ".kz"
    fz = np.fromfile(fname, dtype=np.float32)
    fx = fx.reshape((2, -1))
    fy = fy.reshape((2, -1))
    fz = fz.reshape((2, -1))
    fig = plt.figure(figsize=[7, 5])
    ax = fig.add_axes([0.17, 0.15, 0.75, 0.8])
    ax.loglog(fx[0, :], fx[1, :], linewidth=2, label=r'$x$')
    ax.loglog(fy[0, :], fy[1, :], linewidth=2, label=r'$y$')
    ax.loglog(fz[0, :], fz[1, :], linewidth=2, label=r'$z$')
    ax.legend(loc=1, prop={'size': 16}, ncol=1,
              shadow=False, fancybox=False, frameon=False)
    ax.tick_params(labelsize=16)
    ax.set_xlabel(r'$k_x, k_y, k_z (d_e^{-1})$', fontsize=20)
    ax.set_ylabel(r'$f(k_x), f(k_y), f(k_z)$', fontsize=20)
    fdir = '../img/power_spectrum_vkappa/' + pic_run + '/'
    mkdir_p(fdir)
    fname = fdir + var_name + "_" + str(tindex).zfill(5) + ".pdf"
    fig.savefig(fname)
    if show_plot:
        plt.show()
    else:
        plt.close()


def get_cmd_args():
    """Get command line arguments
    """
    default_pic_run = '3D-Lx150-bg0.2-150ppc-2048KNL'
    default_pic_run_dir = ('/global/cscratch1/sd/xiaocan/' + default_pic_run + '/')
    parser = argparse.ArgumentParser(description='Power spectrum of u.kappa')
    parser.add_argument('--pic_run', action="store",
                        default=default_pic_run, help='PIC run name')
    parser.add_argument('--pic_run_dir', action="store",
                        default=default_pic_run_dir, help='PIC run directory')
    parser.add_argument('--species', action="store",
                        default="electron", help='Particle species')
    parser.add_argument('--tframe', action="store", default='0', type=int,
                        help='Time frame')
    parser.add_argument('--multi_frames', action="store_true", default=False,
                        help='whether to analyze multiple frames')
    parser.add_argument('--time_loop', action="store_true", default=False,
                        help='whether to loop over time instead of using joblib')
    parser.add_argument('--tstart', action="store", default='0', type=int,
                        help='starting time frame')
    parser.add_argument('--tend', action="store", default='10', type=int,
                        help='ending time frame')
    parser.add_argument('--var_name', action="store", default="vkappa",
                        help='variable name')
    return parser.parse_args()


def analysis_single_frames(plot_config, args):
    """Analysis for multiple time frames
    """
    plot_spectrum(plot_config)


def process_input(plot_config, args, tframe):
    """process one time frame"""
    plot_config["tframe"] = tframe
    plot_spectrum(plot_config, show_plot=False)


def analysis_multi_frames(plot_config, args):
    """Analysis for multiple time frames
    """
    tframes = range(plot_config["tmin"], plot_config["tmax"] + 1)
    ncores = multiprocessing.cpu_count()
    if args.time_loop:
        for tframe in tframes:
            plot_config["tframe"] = tframe
            plot_spectrum(plot_config, show_plot=False)
    else:
        Parallel(n_jobs=ncores)(delayed(process_input)(plot_config, args, tframe)
                                for tframe in tframes)


def main():
    """business logic for when running this module as the primary one!"""
    args = get_cmd_args()
    plot_config = {}
    plot_config["pic_run"] = args.pic_run
    plot_config["pic_run_dir"] = args.pic_run_dir
    plot_config["tframe"] = args.tframe
    plot_config["tmin"] = args.tstart
    plot_config["tmax"] = args.tend
    plot_config["species"] = args.species
    plot_config["var_name"] = args.var_name
    if args.multi_frames:
        analysis_multi_frames(plot_config, args)
    else:
        analysis_single_frames(plot_config, args)


if __name__ == "__main__":
    main()
