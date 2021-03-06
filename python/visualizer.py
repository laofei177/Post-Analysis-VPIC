"""
Visualizer of the particle velocity distribution.
"""
import collections
import math
import os
import os.path
import struct

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import rc
from matplotlib.colors import LogNorm
from matplotlib.ticker import MaxNLocator
from matplotlib.widgets import Button, Cursor, Slider
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.mplot3d import Axes3D
from scipy import signal
from scipy.fftpack import fft2, fftshift, ifft2
from scipy.interpolate import spline
from scipy.ndimage.filters import generic_filter as gf

import colormap.colormaps as cmaps
import pic_information
from contour_plots import plot_2d_contour, read_2d_fields
from energy_conversion import read_jdote_data, read_data_from_json
from particle_distribution import get_particle_distribution, set_mpi_ranks

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


class viewer_2d(object):
    def __init__(self, z, x, y, pic_info, base_directory):
        """
        Shows a given array in a 2d-viewer.
        Input: z, an 2d array.
        x,y coordinters are optional.
        """
        self.x = x
        self.y = y
        self.z = z
        self.pic_info = pic_info
        self.base_directory = base_directory
        self.fig = plt.figure(figsize=(10, 10))

        # Overview
        self.overview = self.fig.add_axes([0.1, 0.7, 0.8, 0.28])
        # vmax = np.min([np.abs(np.min(data)), np.abs(np.max(data))])
        vmin = 0.0
        vmax = np.max(self.z)
        self.im1 = self.overview.imshow(
            self.z,
            cmap=plt.cm.seismic,
            extent=[
                np.min(self.x), np.max(self.x), np.min(self.y), np.max(self.y)
            ],
            aspect='auto',
            origin='lower',
            vmin=vmin,
            vmax=vmax,
            interpolation='bicubic')
        divider = make_axes_locatable(self.overview)
        self.cax = divider.append_axes("right", size="2%", pad=0.05)
        self.cbar = self.fig.colorbar(self.im1, cax=self.cax)
        self.cbar.ax.tick_params(labelsize=16)
        self.overview.tick_params(labelsize=16)
        self.overview.set_ylabel(r'$z/d_i$', fontdict=font, fontsize=20)
        self.overview.autoscale(1, 'both', 1)

        # Vertical and Horizontal cut
        xs, ys = 0.06, 0.3
        w1, h1 = 0.4, 0.3
        self.xcut_ax = self.fig.add_axes([xs, ys, w1, h1])
        self.ycut_ax = self.fig.add_axes([xs + w1 + 0.1, ys, w1, h1])

        # Slider to choose time frame
        self.sliderax = plt.axes([0.1, 0.1, 0.8, 0.03])
        time_frames = np.arange(1, self.pic_info.ntp + 1)
        self.slider = DiscreteSlider(self.sliderax,'Time Frame', 1, 10,\
                allowed_vals=time_frames, valinit=time_frames[5])
        self.slider.on_changed(self.update)

        self.cursor = Cursor(
            self.overview, useblit=True, color='black', linewidth=2)
        self.reset_ax = plt.axes([0.7, 0.05, 0.06, 0.04])
        self.reset_button = Button(self.reset_ax, 'Reset')
        self._widgets = [self.cursor, self.reset_button, self.slider]
        self.reset_button.on_clicked(self.clear_xy_subplots)
        self.fig.canvas.mpl_connect('button_press_event', self.click)

    def update(self, val):
        ct = self.slider.val
        ratio = self.pic_info.particle_interval / self.pic_info.fields_interval
        kwargs = {
            "current_time": ct * ratio,
            "xl": 0,
            "xr": 200,
            "zb": -50,
            "zt": 50
        }
        fname = "../../data/by.gda"
        x, z, data = read_2d_fields(self.pic_info, fname, **kwargs)
        self.im1.set_data(data)
        self.fig.canvas.draw_idle()

    def clear_xy_subplots(self, event):
        """Clears the subplots."""
        for j in [self.overview, self.xcut_ax, self.ycut_ax]:
            j.lines = []
            j.legend_ = None
        plt.draw()

    def click(self, event):
        """
        What to do, if a click on the figure happens:
            1. Check which axis
            2. Get data coord's.
            3. Plot resulting data.
            4. Update Figure
        """
        if event.inaxes == self.overview:
            #Get nearest data
            xpos = np.argmin(np.abs(event.xdata - self.x))
            ypos = np.argmin(np.abs(event.ydata - self.y))

            #Check which mouse button:
            if event.button == 1:
                #Plot it                
                c, = self.ycut_ax.plot(
                    self.y, self.z[:, xpos], label=str(self.x[xpos]))
                self.ycut_ax.set_xlim([np.min(self.y), np.max(self.y)])
                self.overview.axvline(self.x[xpos], color=c.get_color(), lw=2)
                p1, = self.overview.plot(
                    self.x[xpos], self.y[ypos], marker='*', markersize=20)

            elif event.button == 3:
                #Plot it                
                c, = self.xcut_ax.plot(
                    self.x, self.z[ypos, :], label=str(self.y[ypos]))
                self.xcut_ax.set_xlim([np.min(self.x), np.max(self.x)])
                self.overview.axhline(self.y[ypos], color=c.get_color(), lw=2)

            xpos = event.xdata
            ypos = event.ydata
            particle_interval = self.pic_info.particle_interval
            pos = [xpos, 0.0, ypos]
            if event.button == 1:
                sizes = np.ones(3) * 8
                corners, mpi_ranks = set_mpi_ranks(self.pic_info, pos, sizes)
                ct = self.slider.val * particle_interval
                print self.slider.val
                get_particle_distribution(self.base_directory, self.pic_info,
                        ct, corners, mpi_ranks)

        plt.draw()


class DiscreteSlider(Slider):
    """A matplotlib slider widget with discrete steps."""

    def __init__(self, *args, **kwargs):
        """
        Identical to Slider.__init__, except for the new keyword 'allowed_vals'.
        This keyword specifies the allowed positions of the slider
        """
        self.allowed_vals = kwargs.pop('allowed_vals', None)
        self.previous_val = kwargs['valinit']
        Slider.__init__(self, *args, **kwargs)
        if self.allowed_vals == None:
            self.allowed_vals = [self.valmin, self.valmax]

    def set_val(self, val):
        discrete_val = self.allowed_vals[abs(val - self.allowed_vals).argmin()]
        xy = self.poly.xy
        xy[2] = discrete_val, 1
        xy[3] = discrete_val, 0
        self.poly.xy = xy
        self.valtext.set_text(self.valfmt % discrete_val)
        if self.drawon:
            self.ax.figure.canvas.draw()
        self.val = discrete_val
        if self.previous_val != discrete_val:
            self.previous_val = discrete_val
            if not self.eventson:
                return
            for cid, func in self.observers.iteritems():
                func(discrete_val)


if __name__ == '__main__':
    # pic_info = pic_information.get_pic_info('../../')
    base_directory = '/net/scratch2/guofan/for_Xiaocan/sigma100-lx300/'
    run_name = 'sigma100-lx300'
    picinfo_fname = '../data/pic_info/pic_info_' + run_name + '.json'
    pic_info = read_data_from_json(picinfo_fname)
    ratio = pic_info.particle_interval / pic_info.fields_interval
    ct = 5
    kwargs = {"current_time": 40, "xl": 0, "xr": 300, "zb": -75, "zt": 75}
    fname = base_directory + "/data/bx.gda"
    x, z, bx = read_2d_fields(pic_info, fname, **kwargs)
    fname = base_directory + "/data/by.gda"
    x, z, by = read_2d_fields(pic_info, fname, **kwargs)
    fname = base_directory + "/data/bz.gda"
    x, z, bz = read_2d_fields(pic_info, fname, **kwargs)
    data = np.sqrt(bx * bx + by * by + bz * bz)
    fig_v = viewer_2d(data, x, z, pic_info, base_directory)
    plt.show()
