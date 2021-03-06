#!/usr/bin/env python
################################################################################
#   lidar2dems - utilties for creating DEMs from LiDAR data
#
#   AUTHOR: Matthew Hanson, matt.a.hanson@gmail.com
#
#   Copyright (C) 2015 Applied Geosolutions LLC, oss@appliedgeosolutions.com
#
#   Redistribution and use in source and binary forms, with or without
#   modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice, this
#     list of conditions and the following disclaimer.
#
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions and the following disclaimer in the documentation
#     and/or other materials provided with the distribution.
#
#   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
#   AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
#   IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#   DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
#   FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
#   DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
#   SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
#   CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
#   OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
################################################################################

# Utilities mostly for interfacing with file system and settings


import os
import sys
import glob
from datetime import datetime
import gippy
from gippy.algorithms import CookieCutter
import numpy
from .geo import check_overlap, get_vector_bounds


# File utilities

def get_classification_filename(site, outdir='', slope=None, cellsize=None, suffix=''):
    """ Generate filename for classification """
    fout = '' if site is None else site.Basename() + '_'
    slope, cellsize = class_params(site, slope, cellsize)
    fout = os.path.join(os.path.abspath(outdir), fout + class_suffix(slope, cellsize, suffix))
    return fout


def dem_products(demtype):
    """ Return products for this dem type """
    products = {
        'density': ['count'],
        'dsm': ['idw'],#['idw', 'max'],
        'dtm': ['idw']#['min', 'max', 'idw']
    }
    return products[demtype]


def splitexts(filename):
    """ Split off two extensions """
    bname, ext = os.path.splitext(filename)
    parts = os.path.splitext(bname)
    if len(parts) == 2 and parts[1] in ['.den', '.min', '.max', '.mean', '.idw', '.count']:
        bname = parts[0]
        ext = parts[1] + ext
    return bname, ext


def class_params(feature, slope=None, cellsize=None):
    """ Get classification parameters based on land classification """
    if slope is not None and cellsize is not None:
        return (slope, cellsize)
    else:
        try:
            # TODO - read in from config file ?
            params = {
                '1': (1, 3),    # non-forest, flat
                '2': (1, 2),    # forest, flat
                '3': (5, 2),    # non-forest, complex
                '4': (10, 2),   # forest, complex
            }
            return params[feature['class']]
        except:
            if slope is None:
                slope = '1'
            if cellsize is None:
                cellsize = '3'
            return (slope, cellsize)


def class_suffix(slope, cellsize, suffix=''):
    """" Generate LAS classification suffix """
    return '%sl2d_s%sc%s.las' % (suffix, slope, cellsize)


def find_lasfiles(lasdir='', site=None, checkoverlap=False):
    """" Find lasfiles intersecting with site """
    filenames = glob.glob(os.path.join(lasdir, '*.las'))
    if checkoverlap and site is not None:
        filenames = check_overlap(filenames, site)
    if len(filenames) == 0:
        raise Exception("No LAS files found")
    return filenames


def find_classified_lasfile(lasdir='', site=None, params=('1', '3')):
    """ Locate LAS files within vector or given and/or matching classification parameters """
    bname = '' if site is None else site.Basename() + '_'
    slope, cellsize = params[0], params[1]
    pattern = bname + class_suffix(slope, cellsize)
    filenames = glob.glob(os.path.join(lasdir, pattern))
    if len(filenames) == 0:
        raise Exception("No classified LAS files found")
    return filenames


# Image processing utilities


def create_chm(dtm, dsm, chm):
    """ Create CHM from a DTM and DSM - assumes common grid """
    dtm_img = gippy.GeoImage(dtm)
    dsm_img = gippy.GeoImage(dsm)
    imgout = gippy.GeoImage(chm, dtm_img)

    # set nodata
    dtm_nodata = dtm_img[0].NoDataValue()
    dsm_nodata = dsm_img[0].NoDataValue()
    nodata = dtm_nodata
    imgout.SetNoData(nodata)

    dsm_arr = dsm_img[0].Read()
    dtm_arr = dtm_img[0].Read()

    # ensure same size arrays, clip to smallest
    s1 = dsm_arr.shape
    s2 = dtm_arr.shape
    if s1 != s2:
        if s1[0] > s2[0]:
            dsm_arr = dsm_arr[0:s2[0], :]
        elif s2[0] > s1[0]:
            dtm_arr = dtm_arr[0:s1[0], :]
        if s1[1] > s2[1]:
            dsm_arr = dsm_arr[:, 0:s2[1]]
        elif s2[1] > s1[1]:
            dtm_arr = dtm_arr[:, 0:s1[1]]

    arr = dsm_arr - dtm_arr

    # set to nodata if no ground pixel
    arr[dtm_arr == dtm_nodata] = nodata
    # set to nodata if no surface pixel
    locs = numpy.where(dsm_arr == dsm_nodata)
    arr[locs] = nodata

    imgout[0].Write(arr)
    return imgout.Filename()


def gap_fill(filenames, fout, site=None, interpolation='nearest'):
    """ Gap fill from higher radius DTMs, then fill remainder with interpolation """
    start = datetime.now()
    from scipy.interpolate import griddata
    if len(filenames) == 0:
        raise Exception('No filenames provided!')

    filenames = sorted(filenames)
    imgs = gippy.GeoImages(filenames)
    nodata = imgs[0][0].NoDataValue()
    arr = imgs[0][0].Read()

    for i in range(1, imgs.size()):
        locs = numpy.where(arr == nodata)
        arr[locs] = imgs[i][0].Read()[locs]

    # interpolation at bad points
    goodlocs = numpy.where(arr != nodata)
    badlocs = numpy.where(arr == nodata)
    arr[badlocs] = griddata(goodlocs, arr[goodlocs], badlocs, method=interpolation)

    # write output
    imgout = gippy.GeoImage(fout, imgs[0])
    imgout.SetNoData(nodata)
    imgout[0].Write(arr)
    fout = imgout.Filename()
    imgout = None

    # align and clip
    if site is not None:
        from osgeo import gdal
        # get resolution
        ds = gdal.Open(fout, gdal.GA_ReadOnly)
        gt = ds.GetGeoTransform()
        ds = None
        parts = splitexts(fout)
        _fout = parts[0] + '_clip' + parts[1]
        CookieCutter(gippy.GeoImages([fout]), site, _fout, gt[1], abs(gt[5]), True)
        if os.path.exists(fout):
            os.remove(fout)
            os.rename(_fout, fout)

    print 'Completed gap-filling to create %s in %s' % (os.path.relpath(fout), datetime.now() - start)

    return fout


# GDAL Utility wrappers


def create_vrt(filenames, fout, site=[None], overwrite=False, verbose=False):
    """ Combine filenames into single file and align if given site """
    if os.path.exists(fout) and not overwrite:
        return fout
    cmd = [
        'gdalbuildvrt',
    ]
    if not verbose:
        cmd.append('-q')
    if site[0] is not None:
        bounds = get_vector_bounds(site)
        cmd.append('-te %s' % (' '.join(map(str, bounds))))
    cmd.append(fout)
    cmd = cmd + filenames
    if verbose:
        print 'Combining %s files into %s' % (len(filenames), fout)
    # print ' '.join(cmd)
    # subprocess.check_output(cmd)
    os.system(' '.join(cmd))
    return fout


def create_hillshade(filename):
    """ Create hillshade image from this file """
    fout = os.path.splitext(filename)[0] + '_hillshade.tif'
    sys.stdout.write('Creating hillshade: ')
    sys.stdout.flush()
    cmd = 'gdaldem hillshade %s %s' % (filename, fout)
    os.system(cmd)
    return fout
