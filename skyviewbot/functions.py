#!/usr/bin/env python
"""Functions for skyviewbot"""

# ASTERICS-OBELICS Good Coding Practices (functions.py)
# V.A. Moss (vmoss.astro@gmail.com), with suggestions from T.J. Dijkema

import os
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from astroquery.skyview import SkyView
from astropy.coordinates import SkyCoord
import astropy.units as u
import logging
import aplpy
import matplotlib.pyplot as plt
import matplotlib as mpl
import tempfile
import requests

# Set matplotlib plotting parameters
# This is because the defaults are sub-optimal
# Maybe you can think of a better way to handle these parameters ;)
mpl.rcParams['xtick.direction'] = 'in'
mpl.rcParams['ytick.direction'] = 'in'
mpl.rcParams['xtick.top'] = True
mpl.rcParams['ytick.right'] = True


logger = logging.getLogger(__name__)


def call_skyview(survey, pos, fov, coord, fitsname, proj='Car', pix=500):
    """Call Skyview to download data from a survey based on input parameters

    Args:
        survey (str): name of survey, from https://skyview.gsfc.nasa.gov/current/cgi/survey.pl
        pos (float,float): position coordinates as a tuple
        fov (float): FOV in degrees
        coord (str): coordinate system (e.g. Galactic, J2000, B1950)
        fitsname (str): name of output fits file
        proj (str): projection of image. (e.g. Car, Sin)
        pix (int): pixel dimensions of image (e.g. 500)

    Examples:
        >>> call_skyview('DSS', (255.291,-29.911), 5., 'J2000', '/tmp/bla.fits')
        >>> call_skyview('NVSS', (144.99497,-01.22029), 0.5, 'Gal', '/tmp/bla.fits')
    """

    x, y = pos

    images = SkyView.get_images(SkyCoord(ra=x*u.deg, dec=y*u.deg), survey,
                                coordinates=coord,
                                projection=proj, pixels=pix,
                                height=fov*u.deg, width=fov*u.deg)

    images[0][0].writeto(fitsname, overwrite=True)


def upload_to_google(img_path, dry_run=False):
    """Upload a file using Google API to Google Drive folder

    Args:
        filename (str): name of file to upload, including path
        dry_run (bool): dry run

    Returns:
        image_id (str): Google Drive image ID

    Examples:
        >>> upload_to_google("test.jpg", dry_run=True)
        'dummy_google_id'
    """

    # Upload the resulting image to Google Drive
    # This connects to a specific account made for this exercise

    # This is a shared folder so automatically gives uploaded files read/write permission
    folder_id = "1OuvohOT1aBpYBLToG5eIJbfdW-Z5a8Nj"

    if dry_run:
        return "dummy_google_id"

    # Set up authorisation
    gauth = GoogleAuth()
    gauth.LocalWebserverAuth()
    drive = GoogleDrive(gauth)

    with open(img_path, "r") as img_file:
        file_drive = drive.CreateFile({'title': os.path.basename(img_file.name),
                                       "parents": [{"kind": "drive#fileLink", "id": folder_id}]})
        file_drive.SetContentFile(img_path)
        file_drive.Upload()

    # This part returns the Google Drive ID of the file
    # We need this for the Slack upload
    return file_drive['id']


def send_to_slack(msg_color, msg_text, field, slack_id, image_id, dry_run=False):
    """Send a post to Slack using Slack webhooks

    Args:
        msg_color (str): any of 'good','warning', 'danger' or a HEX color
        msg_text (str): text of choice to accompany the post
        field (str): name of the field shown in the image posted
        slack_id (str): poster's Slack ID e.g. 'UH0H2QFC2'
        image_id (str): id of chosen image from Google Drive upload
        dry_run (bool): just generate the command, don't execute it

    Returns:
        str: the system command that's used to send this to slack (can be ignored)

    Examples:
        >>> send_to_slack('#3A143E', 'Test', 'Test', 'UH0H2QFC2', '1qWyC6xAHODREDfoZLH4qTYTDwt5m3EEk', dry_run=True)
        {'attachments': [{'color': '#3A143E', 'author_name': '<@UH0H2QFC2>', 'title': 'SkyviewBot Image Post: Test',\
 'text': 'Test', 'image_url': 'http://drive.google.com/uc?export=download&id=1qWyC6xAHODREDfoZLH4qTYTDwt5m3EEk'}]}
    """

    # Replace characters in message text
    msg_text = msg_text.replace("'", "")

    # Construct the full message
    full_msg = {
        "attachments": [
            {
                "color": msg_color,
                "author_name": "<@{}>".format(slack_id),
                "title": "SkyviewBot Image Post: {}".format(field),
                "text": msg_text,
                "image_url": "http://drive.google.com/uc?export=download&id={}".format(image_id)
            }
        ]
    }

    if not dry_run:
        requests.post("https://hooks.slack.com/services/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", json=full_msg)

    return full_msg


def coords_from_name(field_name):
    """Get ra, dec coordinates from a field name using astropy

    Args:
        field_name (str): Field name, e.g. 'M101'

    Returns:
        (float, float): ra, dec in degrees

    Example:
        >>> coords_from_name('M101')
        (210.80242917, 54.34875)
    """
    coord = SkyCoord.from_name(field_name)

    return coord.ra.to(u.deg).value, coord.dec.to(u.deg).value


def plot_fits(fits_name, plot_title, cmap_name, colorbar, output_name):
    """Make a JPEG plot out of a FITS file
    
    Args:
        fits_name (str): path of fits file
        plot_title (str): plot title
        cmap_name (str): name of colormap
        colorbar (bool): include colorbar
        output_name (str): where to save the output
    """
    f = aplpy.FITSFigure(fits_name, figsize=(10, 8))
    plt.title(plot_title)
    f.show_colorscale(cmap=cmap_name, stretch='linear')
    f.ticks.set_color('k')
    if colorbar:
        f.add_colorbar()

    # Note: bbox_inches='tight' gets rid of annoying white space, very useful!
    if output_name:
        plt.savefig(output_name, dpi=200, bbox_inches='tight')


def skyviewbot(slack_id, fieldname, fits_name, msg_text, survey, radius, colormap, dry_run=False):
    """

    Args:
        slack_id (str): Slack ID
        fieldname (str): Field, e.g. "M101" or "255.2,1" (if it contains a comma,
                         it's interpreted as coordinates, otherwise fed to CDS)
        fits_name (str): Name of fits file
        msg_text (str): Message text
        survey (str): Survey, e.g. "DSS"
        radius (float): Radius
        colormap (str): Colormap, e.g. "viridis"
        dry_run (bool): Make image, do not post to slack or google

    Returns:
        bool: True if everything went well
    """
    if ',' in fieldname:
        ra_str, dec_str = fieldname.split(',')
        ra, dec = float(ra_str), float(dec_str)
    else:
        ra, dec = coords_from_name(fieldname)

    if not dry_run and not os.path.isfile("client_secrets.json"):
        logger.error("To upload to Google, you need client_secrets.json in your working directory")
        return False

    if fits_name:
        tempfitsfile = None
    else:
        tempfitsfile = tempfile.NamedTemporaryFile(suffix='.fits')
        fits_name = tempfitsfile.name
        call_skyview(survey, (ra, dec), radius, 'J2000', fits_name)

    # Make an image using aplpy and upload it to google
    with tempfile.NamedTemporaryFile(suffix='.jpg') as tmpfile:
        img_name = tmpfile.name
        plot_fits(fits_name, fieldname, colormap, True, img_name)
        image_id = upload_to_google(img_name, dry_run=dry_run)

    # Send the results to Slack
    msg_color = '#3D99DD'
    send_to_slack(msg_color, msg_text, fieldname, slack_id, image_id, dry_run=dry_run)

    return True

if __name__ == '__main__':
    import doctest
    doctest.testmod()
