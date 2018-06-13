from __future__ import absolute_import, unicode_literals
from backend.celery import app
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from PIL.IptcImagePlugin import getiptcinfo
from django.utils import timezone
from django.contrib.gis.geos import Point
from django.contrib.auth.models import User
from os import stat
from pwd import getpwuid
import logging
import glob
import datetime
import re
import os
from backend.models import StoredFile, Tag


IGNORE = [
    "env",
    ".local",
    ".git",
]

def find_owner(filename):
    return getpwuid(stat(filename).st_uid).pw_name

@app.task
def find_and_process_by_path(path):
    if not path.endswith("**"):
        path = path + "**"

    for filename in glob.iglob(path, recursive=True):
        print("Checking", filename)
        will_ignore = False
        for ignore in IGNORE:
            if re.match(ignore, filename):
                print("IGNORING", filename)
                will_ignore = True
                break

        if not will_ignore:
            print("PROCESSING", filename)
            process_file_by_path.delay(filename)

    return path


@app.task
def process_file_by_path(path):
    print("PROCESSING ONE FILE", path)
    if not os.path.isfile(path):
        print ("NOT A FILE", path)
        return

    try:
        sf = StoredFile.objects.get(content=path)
    except StoredFile.DoesNotExist:
        # If it does NOT have an entry, create one
        sf = StoredFile(
            content=path
        )
        sf.save()

    uid = find_owner(path)
    user, _ = User.objects.get_or_create(username=uid)
    sf.user = user

    sf.save()

    if path[-4:] in ['.jpg', 'jpeg']:
        process_jpeg_metadata.delay(path)

    return sf.id


def get_exif_data(image):
    """Returns a dictionary from the exif data of an PIL Image item. Also converts the GPS Tags"""
    exif_data = {}
    info = image._getexif()
    if info:
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                gps_data = {}
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_data[sub_decoded] = value[t]

                exif_data[decoded] = gps_data
            else:
                exif_data[decoded] = value
    return exif_data


def get_iptc_data(image):
    data = getiptcinfo(image)
    if not data:
        return {}

    data["Keywords"] = [t.decode() for t in data.get((2, 25), [])]
    data["Title"] = data.get((2, 5), b"").decode()
    return data


def get_lat_lng(image):
    """Returns the latitude and longitude, if available, from the provided exif_data (obtained through get_exif_data above)"""
    lat = None
    lng = None
    exif_data = get_exif_data(image)
    # print(exif_data)
    if "GPSInfo" in exif_data:
        gps_info = exif_data["GPSInfo"]
        gps_latitude = gps_info.get("GPSLatitude", None)
        gps_latitude_ref = gps_info.get('GPSLatitudeRef', None)
        gps_longitude = gps_info.get('GPSLongitude', None)
        gps_longitude_ref = gps_info.get('GPSLongitudeRef', None)
        if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
            lat = convert_to_degress(gps_latitude)
            if gps_latitude_ref != "N":
                lat = 0 - lat
            lng = convert_to_degress(gps_longitude)
            if gps_longitude_ref != "E":
                lng = 0 - lng
    return lat, lng


def convert_to_degress(value):

    """Helper function to convert the GPS coordinates
    stored in the EXIF to degress in float format"""
    d0 = value[0][0]
    d1 = value[0][1]
    d = float(d0) / float(d1)

    m0 = value[1][0]
    m1 = value[1][1]
    m = float(m0) / float(m1)

    s0 = value[2][0]
    s1 = value[2][1]
    s = float(s0) / float(s1)

    return d + (m / 60.0) + (s / 3600.0)


@app.task
def process_jpeg_metadata(path):
    # Determine if this object already has an entry in the data_hub DataFile table
    try:
        # Key in an s3 object is the same as the content charfield in the DataFile table.
        # Django does the work under the hood to let you treat this like a file object, but when
        # You are querying, you can search the database by the full S3 object key
        sf = StoredFile.objects.get(content=path)
    except StoredFile.DoesNotExist:
        # If it does NOT have an entry, create one
        sf = StoredFile(
            content=path
        )
        sf.save()

    if sf.processor_metadata is None:
        sf.processor_metadata = {}

    sf.processor_metadata['jpeg_metadata_started'] = timezone.now().isoformat()

    img = Image.open(sf.content)
    exif = get_exif_data(img)
    lat, lng = get_lat_lng(img)
    if lat and lng:
        sf.location = Point(lng, lat)

    # Set "start" datetime based on EXIF formatted date
    if exif.get('DateTimeOriginal'):
        sf.start = datetime.datetime.strptime(exif['DateTimeOriginal'], "%Y:%m:%d %H:%M:%S")
    elif exif.get('DateTime'):
        sf.start = datetime.datetime.strptime(exif['DateTime'], "%Y:%m:%d %H:%M:%S")

    # Some programs use IPTC data for keywords and tags
    iptc = get_iptc_data(img)
    if iptc.get('Keywords', []):
        for tagname in iptc["Keywords"]:
            tag, _ = Tag.objects.get_or_create(name=tagname)
            sf.tags.add(tag)

    # Not all exif fields are json serializable
    # sf.metadata = exif

    sf.metadata = {
        "width": img.width,
        "height": img.height,
    }
    sf.kind = "Image"
    sf.mime_type = "image/jpeg"
    sf.save()
