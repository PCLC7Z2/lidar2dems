#!/usr/bin/env python

"""
Creates density image of all files
"""

import os
from datetime import datetime
from l2d import l2dParser, create_dem, create_dem_piecewise
from gippy import GeoVector


def main():
    parser = l2dParser(description='Create DEM(s) from LiDAR files', commands=True)
    parser.add_input_parser()
    parser.add_output_parser()
    parser.add_filter_parser()
    args = parser.parse_args()

    start0 = datetime.now()

    # open vectors
    if args.site is not None:
        args.site = GeoVector(args.site)
    if args.features is not None:
        args.features = GeoVector(args.features)

    # make sure outdir exists
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    # run piecewise if given processing features
    if args.features is None:
        del args.features
        func = lambda **kwargs: create_dem(**kwargs)
    else:
        func = lambda **kwargs: create_dem_piecewise(**kwargs)

    # create dems for each given radius
    radii = args.radius 
    del args.radius
    for rad in radii:
        func(radius=rad, **vars(args))

    print 'Complete in %s' % (datetime.now() - start0)


if __name__ == '__main__':
    main()
