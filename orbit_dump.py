#!/usr/bin/env python
#
#-----------------------------------------------------------------------------
# Project:     Apex
# Name:        scripts/apex_geo_postprocess.py
# Purpose:     Apex automatic GEO observation postprocessing script
#
# Author:      Vladimir Kouprianov (V.K@BK.ru)
#
# Created:     2006-02-04
# RCS-ID:      $Id: apex_geo_postprocess.py 1615 2013-11-19 10:17:21Z vk $
# Copyright:   (c) 2006-2013 ISON
#-----------------------------------------------------------------------------
"""
apex_geo_postprocess.py - postprocessing of GEO observations: object
identification, orbit determination, and accuracy checking

This Apex script reads a file containing GEO observation results in any of the
supported formats, attempts to find a GEO catalog match for each observation by
RA and Dec, then fits an orbit to each set of observations comprising a short
arc and, finally, computes residuals of individual observations with respect to
this orbit. The latter can serve as a guideline to make a decision whether any
further processing of particular observations is required or measurement
quality is sufficient.

Usage:
  python apex_geo_postprocess.py <filename> [<options>]

<filename> is the name of file containing observation processing results. Any
standard report file format generated by Apex is acceptable.

Output is written to a file with ".check" suffix appended to the input file
name.

Script-specific options:
  dump_orbit = 0 | 1
    dump orbital elements to .check file in a human-readable form; default: 0
  max_track_len = <positive float>
    maximum allowed duration of a single track, minutes; default: 300
  save_orbit = none | uncorrelated | all
    save orbital elements to files; none - don't save (default), uncorrelated -
    only for uncorrelated objects, all - for all objects
  split_by_match = 0 | 1
    split series in .check file according to catalog match; default: 0
"""

import sys
if len(sys.argv) < 2:
    print __doc__
    sys.exit(1)

builtin_sum = sum

# Note. Any of the Apex library modules should be imported prior to non-builtin
#       Python modules in frozen mode since they all are in apex.lib and become
#       accessible only after apex/__init__.py is loaded.
import apex.conf
import apex.sitedef
from apex.timescale import cal_to_mjd, utc_to_lst
from apex.astrometry.precession import prenut
from apex.math.functions import sind, cosd, sinhr, coshr
from apex.io import imheader
from apex.catalog import suitable_catalogs, catalogs, match_objects, query_id
from apex.extra.GEO.report import geo_report_formats
from apex.extra.GEO.geo_catalog import GEO_Catalog
from apex.extra.GEO.satellite_orbit import (state_to_elem, fit_orbit,
    FitSatellite)
from apex.extra.GEO.astrodynamics import ecc_from_mean, mu
from apex.extra.GEO.propagation import (compute_ephemeris, ephem_helper,
    orbit_propagators)

import os.path
from glob import glob
from datetime import date, time, timedelta
from numpy import (arctan, array, asarray, clip, concatenate, cos, cross,
    deg2rad, dot, log10, median, pi, rad2deg, sin, sqrt, tan, transpose, where)


# Script-specific options
dump_orbit = True
max_track_len = apex.conf.Option('max_track_len', 300.0,
    'Maximum allowed duration of a single track, minutes',
    constraint = 'max_track_len > 0')
save_orbit = apex.conf.Option('save_orbit', 'none',
    'Save orbital elements to files', enum = ('none', 'uncorrelated', 'all'))
split_by_match = apex.conf.Option('split_by_match', False,
    'Split series in .check file according to catalog match')


# Initial orbit determination with outlier rejection

def find_orbit(ra, dec, mjds, site):
    N = len(mjds)
    orbit, tan_residuals, norm_residuals, tan_sigma, norm_sigma, \
        tan_outliers, norm_outliers = fit_orbit(ra, dec, mjds, site)
    tan_flags = [(' ', '*')[i in tan_outliers] for i in range(N)]
    norm_flags = [(' ', '*')[i in norm_outliers] for i in range(N)]

    return (orbit, tan_residuals, median(tan_residuals), tan_sigma,
        norm_residuals, median(norm_residuals), norm_sigma, tan_flags,
        norm_flags)


def print_element(output, orbit, match_orbits, elem):
    attr = {'a': 'a', 'e': 'ecc', 'i': 'incl', 'W': 'raan', 'w': 'argp',
            'M': 'anmean'}[elem]
    if elem == 'a':
        unit = 'km'
    elif elem == 'e':
        unit = None
    else:
        unit = 'deg'

    if orbit is not None:
        if elem in ('a', 'p'):
            if abs(orbit.ecc - 1) < 1e-8:
                attr = 'p'
            else:
                attr = 'a'
        print >> output, '  %s%s' % (orbit._format_elem(elem, attr, unit),
                                     ' (IOD)' if match_orbits else '')
    for i, (obj_id, match_orbit) in enumerate(match_orbits):
        if elem in ('a', 'p'):
            if abs(match_orbit.ecc - 1) < 1e-8:
                attr = 'p'
            else:
                attr = 'a'
        name_needed = orbit is None and not i
        print >> output, '  %s%s (%s)' % ('' if name_needed else '   ',
            match_orbit._format_elem(elem if name_needed else '', attr, unit),
            obj_id)

    # if len(match_orbits) + int(orbit is not None) > 1:
        # print >> output


def main():
    # Read and parse the input file; cannot do this with load_measurements(),
    # as we'll need to know the actual report format to do correct rounding of
    # epochs of measurements
    filename = sys.argv[1]
    print '\nPostprocessing observations from file %s' % filename
    blocks = None
    for report_fmt in geo_report_formats.plugins.itervalues():
        try:
            blocks = report_fmt.load_measurements(filename)
            if blocks:
                print 'Loaded %d measurement(s) from "%s" (%s)' % (
                    sum([len(measurements)
                         for measurements in blocks.itervalues()]),
                    filename, report_fmt.descr)
                break
        except:
            pass
    if not blocks:
        print 'Unable to recognize measurement file format or no ' \
           'measurements in file "%s"' % filename
        return

    # Obtain image file names
    print 'Retrieving measurement epochs'
    frames = {}
    for fn in glob('*'):
        if os.path.splitext(fn)[1].lower() not in ('.proclog', '.apex',
                                                   '.metadata'):
            try:
                # Round epoch to precision used by report format
                frames[report_fmt.parse_epoch(report_fmt.format_epoch(
                    imheader(fn)[0].obstime))] = fn
            except:
                pass

    # Obtain the list of catalogs for identification and match all measurements
    # to these catalogs; the dictionary "matches", indexed by pairs
    # (tag,epoch), will contain CatalogObject instances that match the given
    # measurements
    match_catalogs = [id for id in suitable_catalogs('ident')
                      if isinstance(catalogs.plugins[id], GEO_Catalog)]
    matches = {}
    if match_catalogs:
        # For greater efficiency, we obtain the list of observation epochs and
        # perform identification for all measurements referring to the same
        # epoch at once - this allows to compute all catalog satellite
        # ephemerides only once per epoch
        print '\nPerforming identification with', match_catalogs
        epochs = list(set(builtin_sum([blocks[tag].keys() for tag in blocks],
                                      [])))
        epochs.sort()

        for epoch_num, epoch in enumerate(epochs):
            print '\nMatching observations for epoch %s (%d of %d)' % \
                (epoch, epoch_num + 1, len(epochs))

            # Retrieve measurements for the given epoch
            tags, objs = zip(*[(tag, blocks[tag][epoch]) for tag in blocks
                               if epoch in blocks[tag]])

            # Match all objects for the current epoch
            obj_matches = match_objects(objs, match_catalogs, epoch)

            # Save all objects for which a match has been found
            for tag, match in zip(tags, obj_matches):
                if match is not None:
                    matches[tag, epoch] = match

            print '%d of %d measurement(s) identified' % \
                (len(obj_matches) - obj_matches.count(None), len(obj_matches))

    # Obtain station coordinates
    latitude = apex.sitedef.latitude.value
    longitude = apex.sitedef.longitude.value
    altitude = apex.sitedef.altitude.value

    # List of matches for ident.txt
    match_list = []

    # Output report
    filename += '.check'
    with open(filename, 'wt') as f:
        # Process each target sequentially
        for tag in sorted(blocks):
            print '\n\n\nProcessing target: %s' % (tag,)
            measurements = blocks[tag]
            if not measurements:
                continue

            # Retrieve epochs, coordinates, and magnitudes
            epochs = list(sorted(measurements))
            mjd = asarray([cal_to_mjd(ep) for ep in epochs])
            mjd0 = int(mjd[0])
            ra, dec, mag = transpose([
                (obj.ra, obj.dec, obj.mag if hasattr(obj, 'mag') else 0)
                for obj in [measurements[ep] for ep in epochs]])

            # Convert RA to HA
            ha = ([utc_to_lst(ep) for ep in epochs] - ra) % 24

            # Retrieve image file names
            frame_names = [frames.get(t) for t in epochs]

            # Split the full data for the current object into series by match
            # name (if split_by_match is set), each series being not longer
            # than max_track_len minutes
            series = []
            matches_for_target = {str(matches[tag, epoch].id)
                 if (tag, epoch) in matches and hasattr(matches[tag, epoch],
                                                        'id')
                 else '?' for epoch in epochs}
            print '\nMatches:', ', '.join(matches_for_target)
            if not split_by_match.value:
                matches_for_target = ['']
            for match_id in matches_for_target:
                if split_by_match.value:
                    # Extract only measurements for the current match_id
                    indices = []
                    for i, epoch in enumerate(epochs):
                        has_match = (tag, epoch) in matches and \
                                    hasattr(matches[tag, epoch], 'id')
                        if has_match and \
                           matches[tag, epoch].id == match_id or \
                           not has_match and match_id == '?':
                            indices.append(i)
                else:
                    # Use all measurements
                    indices = range(len(epochs))

                frame_names_for_match = [frame_names[i] for i in indices]
                epochs_for_match = [epochs[i] for i in indices]
                mjd_for_match = mjd[indices]
                ra_for_match = ra[indices]
                ha_for_match = ha[indices]
                dec_for_match = dec[indices]
                mag_for_match = mag[indices]

                # Split by duration of series
                istart = 0
                for i, t in enumerate(mjd_for_match):
                    if i == len(mjd_for_match) - 1:
                        # Last record; force end of series
                        iend = i + 1
                    elif (t - mjd_for_match[istart]) > \
                         max_track_len.value/(60.0*24):
                        # New series starts; finish the previous one
                        iend = i
                    else:
                        # Current series continues
                        continue
                    # Append the finished series
                    series.append((frame_names_for_match[istart:iend],
                                   epochs_for_match[istart:iend],
                                   mjd_for_match[istart:iend],
                                   ra_for_match[istart:iend],
                                   ha_for_match[istart:iend],
                                   dec_for_match[istart:iend],
                                   mag_for_match[istart:iend]))
                    print '\nObservation series %d: %d measurement(s)' % \
                        (len(series), iend - istart)
                    istart = iend

            # List of tuples (id, num, totnum, dtan, dnorm) for the current
            # target
            matches_for_target = []

            # Process all series for the current target
            print >> f, ('-- Target: %s ' % (tag,)).ljust(150, '-')
            if len(series) > 1:
                print >> f, '\nWARNING. Measurements possibly contain ' \
                    'multiple objects'
            for sernum, (frame_names, epochs, mjd, ra, ha, dec, mag) in \
                  enumerate(series):
                print '\n\nProcessing series #%d' % (sernum + 1)

                # Transform coordinates to TOD
                ra_tod, dec_tod = asarray(zip(*
                    [prenut(alpha, delta, 2000.0, t, True)
                     for alpha, delta, t in zip(ra, dec, mjd)]))

                # Format magnitudes and internal residuals for output
                str_mag = ['%5.2f' % m if m else '' for m in mag]

                # Fit an orbit to the current series and compute residuals with
                # respect to this orbit
                print '\nPerforming initial orbit determination'
                site = (latitude, longitude, altitude)
                try:
                    orbit, tan_residuals, tan_mean, tan_rms, norm_residuals, \
                        norm_mean, norm_rms, tan_flags, norm_flags = \
                        find_orbit(ra_tod, dec_tod, mjd, site)

                    # Format internal residuals for output
                    str_int_tan_residuals = \
                        ['%+09.2f' % d if d is not None else ''
                         for d in tan_residuals]
                    str_int_norm_residuals = \
                        ['%+09.2f' % d if d is not None else ''
                         for d in norm_residuals]
                except Exception as E:
                    print '\nOrbit determination failed:', E
                    orbit = tan_mean = norm_mean = tan_rms = norm_rms = None
                    str_int_tan_residuals = str_int_norm_residuals = \
                        ['']*len(mjd)
                    tan_flags = norm_flags = [' ']*len(mjd)

                # Format matches and compute external residuals for
                # measurements that have matches
                ext_tan_residuals, ext_norm_residuals, str_match = [], [], []
                sublons = []
                match_ids = set()
                for i, epoch in enumerate(epochs):
                    try:
                        match = matches[tag, epoch]

                        # Construct the full matching object ID
                        try:
                            full_match_id = str(match.id)
                        except:
                            full_match_id = '?'
                        try:
                            full_match_id += '/%s' % match.intl_id
                        except AttributeError:
                            pass
                        try:
                            full_match_id += ' (%s)' % match.name
                        except AttributeError:
                            pass

                        # Compute ephemeris for the same epoch
                        catobj = query_id(match.id, match.catid, epoch,
                                          silent = True)[0]
                        match_ids.add((match.id, match.catid))
                        sublons.append(catobj.sublon)

                        # Compute tangential/normal residuals
                        pv0 = concatenate(apex.sitedef.obs_eci(latitude,
                            altitude, utc_to_lst(epoch, longitude/15,
                                apparent = False))[:2])*\
                            (1e-3/apex.sitedef.km_per_AU)
                        pv = concatenate([catobj.p, catobj.v])/ \
                            apex.sitedef.km_per_AU
                        apex.sitedef.apply_topo(pv, pv0)
                        e1 = pv[:3]
                        e1 /= sqrt((e1**2).sum())
                        e2 = pv[3:] - dot(pv[3:], e1)*e1
                        e2 /= sqrt((e2**2).sum())
                        e3 = cross(e1, e2)
                        I = [cosd(dec_tod[i])*coshr(ra_tod[i]),
                             cosd(dec_tod[i])*sinhr(ra_tod[i]),
                             sind(dec_tod[i])]
                        krad = 180/pi*3600
                        dtan = dot(I, e2)*krad
                        dnorm = dot(I, e3)*krad

                        str_match.append(full_match_id)
                        ext_tan_residuals.append(dtan)
                        ext_norm_residuals.append(dnorm)
                        matches_for_target.append((full_match_id[:40], dtan,
                                                   dnorm))
                    except:
                        str_match.append('')
                        ext_tan_residuals.append(None)
                        ext_norm_residuals.append(None)

                # Sub-point longitude
                if sublons:
                    sublons = asarray(sublons)
                    if where(sublons < 90)[0].any() and \
                       where(sublons > 270)[0].any():
                        sublons[sublons > 180] -= 360
                    sublon = median(sublons) % 360
                else:
                    sublon = None

                # Deal with external residuals
                d = array([d for d in ext_tan_residuals if d is not None])
                if len(d):
                    ext_tan_mean = median(d)
                    ext_tan_rms = sqrt(((d - ext_tan_mean)**2).mean())
                else:
                    ext_tan_mean = ext_tan_rms = None
                str_ext_tan_residuals = ['%+09.2f' % d if d is not None else ''
                                         for d in ext_tan_residuals]

                d = array([d for d in ext_norm_residuals if d is not None])
                if len(d):
                    ext_norm_mean = median(d)
                    ext_norm_rms = sqrt(((d - ext_norm_mean)**2).mean())
                else:
                    ext_norm_mean = ext_norm_rms = None
                str_ext_norm_residuals = ['{:+09.2f}'.format(d)
                                          if d is not None else ''
                                          for d in ext_norm_residuals]

                # Compute the maximum frame name width
                fnwidth = max([len(fn) if fn else 0 for fn in frame_names])
                if fnwidth:
                    fnwidth += 2

                # Header
                h = '\n\n%-*s%11s  %10s  %10s  %10s  %5s  %22s  %42s  Match' \
                    '\n%-*s%11s  %-10s  %-10s  %-10s  %5s  %10s  %10s  %9s  ' \
                        '%9s' % \
                    (fnwidth, 'Frame'.center(fnwidth - 2) if fnwidth else '',
                     'MJD - %5d' % mjd0, 'RA'.center(10), 'HA'.center(10),
                     'Dec'.center(10), 'mag'.center(5),
                     'Int. residuals ["]'.center(22),
                     'Ext. residuals ["]'.center(18),

                     fnwidth, '', '', '  h', '  h', '   d', '',
                     'Tangent'.center(10), 'Normal'.center(10),
                     'Tangent.'.center(9), 'Normal'.center(9),
                    )
                print >> f, h

                for res in zip(frame_names, mjd - mjd0, ra, ha, dec, str_mag,
                               str_int_tan_residuals, tan_flags,
                               str_int_norm_residuals, norm_flags,
                               str_ext_tan_residuals, str_ext_norm_residuals,
                               str_match):
                    if fnwidth:
                        s = '%-*s' % (fnwidth, res[0])
                    else:
                        s = ''
                    print >> f, s + '%11.8f  %010.7f  %010.7f  %+010.6f  ' \
                        '%5s  %9s%c  %9s%c  %9s  %9s  %s' % res[1:]

                # Totals
                print >> f, 'Median:' + ' '*(49 + fnwidth) + \
                            '%9s   %9s   %9s  %9s' % \
                    ('%+9.2f' % tan_mean if tan_mean is not None else '',
                     '%+9.2f' % norm_mean if norm_mean is not None else '',
                     '%+9.2f' % ext_tan_mean if ext_tan_mean is not None \
                                else '',
                     '%+9.2f' % ext_norm_mean if ext_norm_mean is not None \
                                else '')
                if tan_rms is not None or norm_rms is not None or \
                   ext_tan_rms is not None or ext_norm_rms is not None:
                    print >> f, 'RMS:' + ' '*(52 + fnwidth) + \
                                '%9s   %9s   %9s  %9s' % \
                        ('%9.2f' % tan_rms if tan_rms is not None else '',
                         '%9.2f' % norm_rms if norm_rms is not None else '',
                         '%9.2f' % ext_tan_rms if ext_tan_rms is not None \
                                   else '',
                         '%9.2f' % ext_norm_rms if ext_norm_rms is not None \
                                   else '')

                # Mark uncorrelated object
                if str_match.count('') == len(str_match):
                    print >> f, '\nWARNING. The object is uncorrelated'

                if orbit is not None and (save_orbit.value == 'all' or
                   save_orbit.value == 'uncorrelated' and
                   str_match.count('') == len(str_match)):
                    # Save orbits of uncorrelated objects to separate files
                    from apex.extra.GEO.geo_catalog import ephem_propagator
                    propagate = orbit_propagators.plugins[
                        ephem_propagator.value].propagate
                    m0 = array(
                        [m - 5*log10(obj.r*apex.sitedef.km_per_AU/1000) +
                         2.5*log10(sin(deg2rad(obj.phase)) +
                         deg2rad(180 - obj.phase)*cos(deg2rad(obj.phase))) -
                         2.5*log10(pi/1600)
                         for m, obj in [(m, compute_ephemeris(
                            FitSatellite(orbit), propagate, 'TEME',
                            *ephem_helper(t, *site)))
                            for m, t in zip(mag, mjd) if m is not None]])
                    t = orbit.epoch.replace(microsecond = 0) + timedelta(
                        microseconds = round(orbit.epoch.microsecond/ \
                                             1000.0)*1000,
                        hours = -apex.timescale.eqeqx(orbit.epoch_mjd))
                    T = 2*pi*sqrt(orbit.p**3/mu)/60
                    with open('{}_{}.orbit'.format(*tag), 'wt') as fo:
                        print >> fo, \
                            '|{:6d}| 0 |999|{:02d}{:02d}{:04d}|{:02d}{:02d}' \
                            '{:02d}.{:03d}|{:+6.1f}|{:+5.1f}|{:10.3f}|' \
                            '{:9.4f}|{:8.4f}|{:8.4f}|{:9.7f}|{:8.4f}|{:8.4f}' \
                            '|  +0.00001|  +0.00001|    1 |+0.0000000|' \
                            '{:5.1f}|{:3.1f}|{:6d}| 0.1|  1(0.1)|'.format(
                            int(tag[1]) % 1000000, t.day, t.month, t.year,
                            t.hour, t.minute, t.second, t.microsecond//1000,
                            sublon if sublon is not None else 0,
                            clip(-0.25*(T - 1436.2), -99, 99), orbit.a, T,
                            orbit.incl, orbit.raan, orbit.ecc, orbit.argp,
                            orbit.argp + 2*rad2deg(arctan(
                                sqrt((1 + orbit.ecc)/(1 - orbit.ecc))*tan(
                                deg2rad(ecc_from_mean(orbit.ecc,
                                    orbit.anmean))/2))),
                            clip(m0.mean(), -99.9, 99.9) if len(m0) else 0,
                            clip(m0.std(), 0, 9.9) if len(m0) > 1 else 0,
                            int(tag[1]) % 1000000,)

                # Orbit
                if dump_orbit:
                    # Obtain osculating elements of matching catalog objects
                    # for the same epoch
                    match_orbits = []
                    if orbit is None:
                        epoch = epochs[0] + (epochs[-1] - epochs[0])/2
                    else:
                        epoch = orbit.epoch
                    for obj_id, obj_catid in sorted(match_ids):
                        catobj = query_id(obj_id, obj_catid, epoch,
                                          silent = True)[0]
                        match_orbits.append((obj_id, state_to_elem(catobj.p,
                                                                   catobj.v)))

                    if orbit is None:
                        if match_orbits:
                            print >> f, 'Osculating elements of catalog ' \
                                'object(s)'
                    else:
                        print >> f, 'Osculating elements for epoch %s:' % \
                            orbit.epoch
                    print_element(f, orbit, match_orbits, 'a')
                    print_element(f, orbit, match_orbits, 'e')
                    print_element(f, orbit, match_orbits, 'i')
                    print_element(f, orbit, match_orbits, 'W')
                    print_element(f, orbit, match_orbits, 'w')
                    print_element(f, orbit, match_orbits, 'M')

                    if sublon is not None:
                        print >> f, 'Longitude of sub-satellite point: ' \
                            '%.1f' % sublon

            # Target finished
            print >> f, '\n'

            # Deal with object identification
            # Each element in the match list is a tuple ([date, tag,
            # [(id,num,totnum,dtan,dnorm), (id,num,totnum,dtan,dnorm),...]),
            # where "date" is UTC date (starting at 12AM) of the first
            # observation, "tag" is object tag (e.g. a pair (station,target))
            # in string representation, and the third element contains a list
            # of catalog matches (id), along with number of observations
            # matching this id, total number of observations, and tangential
            # and normal residuals; id=None means no matches found
            if hasattr(tag, '__getitem__'):
                tagstr = ' '.join(['%06d' % item if isinstance(item, int) \
                                   else '%-6s' % item for item in tag])
            else:
                tagstr = str(tag)
            totnum = len(measurements)
            m = [
                (match_id,
                 len([m for m in matches_for_target if m[0] == match_id]),
                 totnum,
                 median([m[1] for m in matches_for_target
                         if m[0] == match_id])/3600.0,
                 median([m[2] for m in matches_for_target
                         if m[0] == match_id])/3600.0)
                for match_id in {m[0] for m in matches_for_target}]
            if not m:
                m = [(None, totnum, totnum, None, None)]
            match_list.append(
                ([epoch.date() - timedelta(days = 1) if epoch.time() < time(12)
                  else epoch.date()
                  for epoch in list(sorted(measurements))][0], tagstr[:16], m))

    # Update the ident.txt file
    ident = {}
    prev_date = prev_tagstr = None
    try:
        lines = open('ident.txt', 'rU').read().splitlines()

        for line in lines:
            tagstr = line[10:26].strip()
            try:
                curr_date = date(*[int(s) for s in line[:10].split('-')])
                prev_date, prev_tagstr = curr_date, tagstr
            except:
                curr_date = None
            match_str = line[26:].strip()
            if curr_date is None:
                # More matches for the current target
                if prev_date is not None:
                    ident[prev_date, prev_tagstr].append(match_str)
            else:
                # New target
                ident[curr_date, tagstr] = [match_str]
    except:
        pass

    # Sort matches by the number of measurements per match
    for d, tagstr, matches in match_list:
        ident[d, tagstr] = ['%-40s  %3d/%-3d  %6.3f  %6.3f' % \
                           m if m[0] is not None \
                           else '%-40s  %3d' % ('???', m[1])
                           for m in sorted(matches, key = lambda m: m[1],
                                           reverse = True)]

    try:
        with open('ident.txt', 'wt') as f:
            print >> f, """
       Date     Measurements   Match ID/designation                     Num /Total Residual [deg]
                                                                      matched      tan    norm
    """
            for d, tagstr in sorted(ident):
                matches = ident[d, tagstr]
                print >> f, '%10s %-15s %s' % (d, tagstr, matches[0])
                for matchstr in matches[1:]:
                    print >> f, '%26s %s' % ('', matchstr)
    except Exception as E:
        print '\n\nWARNING. Error updating ident.txt:', E

    print '\n\nPostprocessing complete; results written to %s' % filename

if __name__ == '__main__':
    main()
