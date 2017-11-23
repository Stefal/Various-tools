#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function

import os, sys, datetime, time, argparse, exifread
import xml.etree.ElementTree as ET
from collections import namedtuple

Picture_infos = namedtuple('Picture_infos', ['path', 'DateTimeOriginal', 'Longitude', 'Latitude',
                                             'Ele', 'ImgDirection'])


def list_images(directory):
    """
    Create a list of image tuples sorted by capture timestamp.
    @param directory: directory with JPEG files
    @return: a list of image tuples with time, directory, lat,long...
    """
    file_list = []
    for root, sub_folders, files in os.walk(directory):
        file_list += [os.path.join(root, filename) for filename in files if filename.lower().endswith(".jpg")]

    images_list = []
    # get DateTimeOriginal data from the images and sort the list by timestamp
    # using exifread 
    for filepath in file_list:
        with open(filepath, 'rb') as file:
            tags = exifread.process_file(file, details=False)

        # If picture has coordinates and timestamp
        if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags and 'EXIF DateTimeOriginal' in tags:
            # Read and convert latitude
            deg, mn, sec = [ratio_to_float(i) for i in tags['GPS GPSLatitude'].values]
            hemis = tags['GPS GPSLatitudeRef'].values
            lat = DMStoDD(deg, mn, sec, hemis)
            # Read and convert longitude
            deg, mn, sec = [ratio_to_float(i) for i in tags['GPS GPSLongitude'].values]
            hemis = tags['GPS GPSLongitudeRef'].values
            lon = DMStoDD(deg, mn, sec, hemis)
            # Read and convert timestamp
            timestamp = datetime.datetime.strptime(tags['EXIF DateTimeOriginal'].values, "%Y:%m:%d %H:%M:%S")
            # Read, convert, and add subsecond value to the timestamp
            subsec = tags['EXIF SubSecTimeOriginal'].values if 'EXIF SubSecTimeOriginal' in tags else ""
            timestamp.replace(microsecond=int(float("0." + subsec) * 1000000))
            # Read and convert altitude
            altitude = ratio_to_float(list(tags['GPS GPSAltitude'].values)[0]) if 'GPS GPSAltitude' in tags else ""
            # Read and convert bearing
            imgDirection = ratio_to_float(
                list(tags['GPS GPSImgDirection'].values)[0]) if 'GPS GPSImgDirection' in tags else ""

            # create new namedtuple
            images_list.append(Picture_infos(filepath, timestamp, lon, lat, altitude, imgDirection))

    images_list.sort(key=lambda imgfile: imgfile.DateTimeOriginal)
    return images_list


def DMStoDD(degrees, minutes, seconds, hemisphere):
    """ Convert from degrees, minutes, seconds to decimal degrees. """
    dms = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if hemisphere == "W" or hemisphere == "S":
        dms = -1 * dms

    return dms


def ratio_to_float(value):
    """convert a ration to a float value"""
    float_value = float(value.num / value.den)
    return float_value


def write_josm_session(piclists, session_file_path, cam_names, gpx_file=None):
    """
    Build a josm session file in xml format with all the pictures on separate layer, and another
    layer for the gpx/nmea file
    :param piclists: a list of of list of New_Picture_infos namedtuple
    :param session_file_path: the path and name of the session file
    :param cam_names: The camera's name, which will be the layer's name
    :param gpx_file: a list of gpx/nmea filepaths.
    """

    root = ET.Element("josm-session")
    root.attrib = {"version": "0.1"}
    viewport = ET.SubElement(root, "viewport")
    projection = ET.SubElement(root, "projection")
    layers = ET.SubElement(root, "layers")

    # view_center = ET.SubElement(viewport, "center")
    # view_center.attrib = {"lat":"47.7", "lon":"-2.16"}
    # view_scale = ET.SubElement(viewport, "scale")
    # view_scale.attrib = {'meter-per-pixel' : '0.8'}

    proj_choice = ET.SubElement(projection, "projection-choice")
    proj_id = ET.SubElement(proj_choice, "id")
    proj_id.text = "core:mercator"
    proj_core = ET.SubElement(projection, "code")
    proj_core.text = "EPSG:3857"
    # TODO gérer les cas avec des dossiers sans images (les supprimer avant la suite ???)
    # TODO nom du dossier sans l'abspath
    for i, piclist in enumerate(piclists):
        layer = ET.SubElement(layers, "layer")
        layer.attrib = {"index": str(i), "name": str(os.path.basename(cam_names[i])), "type": "geoimage",
                        "version": str(0.1),
                        "visible": "true"}

        show_thumb = ET.SubElement(layer, "show-thumbnails")
        show_thumb.text = "false"

        for pic in piclist:
            geoimage = ET.SubElement(layer, "geoimage")
            g_file = ET.SubElement(geoimage, "file")
            g_file.text = pic.path
            g_thumb = ET.SubElement(geoimage, "thumbnail")
            g_thumb.text = "false"
            g_position = ET.SubElement(geoimage, "position")
            g_position.attrib = {"lat": str(pic.Latitude), "lon": str(pic.Longitude)}
            g_elevation = ET.SubElement(geoimage, "elevation")
            g_elevation.text = str(pic.Ele)
            g_exif_orientation = ET.SubElement(geoimage, "exif-orientation")
            g_exif_orientation.text = "1"
            g_exif_time = ET.SubElement(geoimage, "exif-time")
            # josm concatenate the timestamp second and microsecond (1531241239.643 becomes 1531241239643
            g_exif_time.text = str(int(time.mktime(pic.DateTimeOriginal.timetuple()))) + "%.3d" % round(
                pic.DateTimeOriginal.microsecond / float(1000), 0)
            g_exif_direction = ET.SubElement(geoimage, "exif-image-direction")
            g_exif_direction.text = str(pic.ImgDirection)
            g_is_new_gps = ET.SubElement(geoimage, "is-new-gps-data")
            g_is_new_gps.text = "false"

    if gpx_file is not None:
        for i, gpx in enumerate(gpx_file):
            gpx_layer = ET.SubElement(layers, "layer")
            gpx_layer.attrib = {"index": str(len(piclists) + 1 + i), "name": gpx.split("\\")[-1], "type": "tracks",
                                "version": "0.1", "visible": "true"}
            gpx_file_layer = ET.SubElement(gpx_layer, "file")
            gpx_file_layer.text = "file:/" + gpx.replace("\\", "/")

    myxml = ET.ElementTree(root)

    try:
        os.path.isdir(os.path.split(session_file_path)[0])
        myxml.write(session_file_path)
    except:
        print("The folder to write the session file doesn't exists")
        return myxml


def open_session_in_josm(session_file_path, remote_port=8111):
    """Send the session file to Josm. "Remote control" and "open local files" must be enable in the Josm settings
     :param session_file_path: the session file path (.jos)
     :param remote_port: the port to talk to josm. Default is 8111"""
    import requests, posixpath

    if os.sep != posixpath.sep:
        session_file_path = session_file_path.replace(os.sep, posixpath.sep)

    print("Opening the session in Josm....", end="")
    try:
        r = requests.get("http://127.0.0.1:" + str(remote_port) + "/open_file?filename=" + session_file_path, timeout=5)
        print("Success")
    except requests.exceptions.RequestException as e:
        print(e)

    r.close()


def arg_parse():
    """ Parse the command line you use to launch the script
    """
    parser = argparse.ArgumentParser(description="Script to ", version="0.1")
    parser.add_argument("source", nargs="?",
                        help="Path source of the folders with the pictures. Without this parameter, "
                             "the script will use the current directory as the source", default=os.getcwd())
    parser.add_argument("-g", "--gpxfile", help="Path to the gpx/nmea file. Without this parameter, "
                                                "the script will search in the current directory")
    parser.add_argument("-j", "--josm", help="Load the pictures in Josm (must be running)", action="store_true")

    args = parser.parse_args()
    print(args)
    return args


def find_file(directory, file_extension):
    """Try to find the files with the given extension in a directory
    :param directory: the directory to look in
    :param file_extension: the extension (.jpg, .gpx, ...)
    :return: a list containing the files found in the directory"""
    file_list = []
    for root, sub_folders, files in os.walk(directory):
        file_list += [os.path.join(root, filename) for filename in files if filename.lower().endswith(file_extension)]

    if len(file_list) == 0:
        print("No {0} file found".format(file_extension))

    return file_list


def find_directory(working_dir, strings_to_find):
    """Try to find the folders containing a given string in their names
    :param working_dir: The base folder to search in
    :param strings_to_find: a list of strings to find in the folder's names
    :return: a list of folder with the string_to_find in their name"""
    images_path = []
    dir_list = [i for i in os.listdir(working_dir) if os.path.isdir(i)]
    for string in strings_to_find:
        try:
            images_path.append(os.path.abspath(os.path.join(working_dir, dir_list[dir_list.index(string)])))
        except ValueError:
            print("I can't find {0}".format(string))
            sys.exit()
    return images_path


if __name__ == '__main__':
    # Parsing the command line arguments
    args = arg_parse()

    # Trying to find a nmea file in the working directory if none is given in the command line
    if args.gpxfile is None:
        print("=" * 30)
        args.gpxfile = find_file(args.source, "nmea")
    # Or a gpx file if there is no nmea file
    if args.gpxfile is None:
        args.gpxfile = find_file(args.source, "gpx")

    # Trying to find the folders containing the pictures
    directory_list = [os.path.abspath(i) for i in os.listdir(args.source) if os.path.isdir(i)]

    # Searching for all the jpeg images
    image_list = []
    print("=" * 80)
    print("Searching for jpeg images in ... ")
    for path in directory_list:
        print(path)
        image_list.append(list_images(path))

    # Write a josm session file 
    session_file_path = os.path.abspath(os.path.join(args.source, "session.jos"))
    write_josm_session(image_list, session_file_path, directory_list, args.gpxfile)

    if args.josm:
        open_session_in_josm(session_file_path)
