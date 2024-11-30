# (C) Copyright 2020 Andy Knitt

from wavtoau import convert_wav_to_au
import xml.etree.ElementTree as ET
import xml.dom.minidom
import os
import argparse
import sys
import datetime
import time
import json

# Argument parser setup
parser = argparse.ArgumentParser(description='Build an Audacity multi-track project from multiple talkgroups in trunk-recorder recordings')
parser.add_argument('Path', help='Path to the base trunk-recorder audio recording directory for the system in question')
parser.add_argument('Date', help='Date of the recordings to retrieve in MM/DD/YYYY format')
parser.add_argument('StartTime', help='Start time of the recordings to retrieve in HH:MM:SS format')
parser.add_argument('StopTime', help='End time of the recordings to retrieve in HH:MM:SS format')
parser.add_argument('TGIDS', help='Comma separated list of decimal format talkgroup IDs to retrieve')
parser.add_argument('OutFile', help='Filename of the output Audacity project file. Must end with .aup extension')
parser.add_argument('--splitwav', dest='splitwav', action='store_true', help='When set, split WAV files into multiple segments in the Audacity track based on the logged JSON data. Results in more accurate timing of reconstructed audio. Default is set. Use --no-splitwav for single segments.')
parser.add_argument('--no-splitwav', dest='splitwav', action='store_false', help='When set, a single segment is created in Audacity per WAV file. Default is to use --splitwav')
parser.add_argument('--TGID_CSV', help='CSV file containing TGID names in trunk-recorder format')
parser.set_defaults(splitwav=True)
parser.set_defaults(TGID_CSV='')

args = parser.parse_args()
rpath = args.Path
rdate = args.Date
ryear = rdate.split('/')[2]
rmonth = str(int(rdate.split('/')[0]))
rday = str(int(rdate.split('/')[1]))
start_time = args.StartTime
stop_time = args.StopTime
TGIDS = args.TGIDS.split(',')
outfile = args.OutFile
splitwav = args.splitwav
TGID_CSV = args.TGID_CSV

# Argument validation
if not os.path.isdir(rpath):
    print("Error - Path to the base trunk-recorder audio recording directory not found")
    sys.exit()

rfilepath = rpath + "/" + ryear + "/" + rmonth + "/" + rday
if not os.path.isdir(rfilepath):
    print("Error - No recordings found for date provided")
    sys.exit()

utc_offset = time.timezone if time.daylight == 0 else time.altzone
start_timestamp = (datetime.datetime(int(ryear), int(rmonth), int(rday), int(start_time.split(':')[0]), int(start_time.split(':')[1]), int(start_time.split(':')[2])) - datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=utc_offset)).total_seconds()
stop_timestamp = (datetime.datetime(int(ryear), int(rmonth), int(rday), int(stop_time.split(':')[0]), int(stop_time.split(':')[1]), int(stop_time.split(':')[2])) - datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=utc_offset)).total_seconds()

if start_timestamp > stop_timestamp:
    print("Error - start time is greater than stop time")
    sys.exit()

if outfile[-4:] != '.aup':
    print("Error - invalid output filename - must end in .aup")
    sys.exit()

if TGID_CSV != '' and not os.path.isfile(TGID_CSV):
    print("Error - TGID CSV file does not exist")
    sys.exit()

# Create the "Projects" directory if it doesn't exist
projects_dir = os.path.join(os.getcwd(), "Projects")
if not os.path.isdir(projects_dir):
    os.mkdir(projects_dir)

# Create the folder for the specific project (same name as .aup file)
project_folder = os.path.join(projects_dir, outfile.replace('.aup', ''))
if not os.path.isdir(project_folder):
    os.mkdir(project_folder)

# Create the _data directory inside the project folder
datadir = os.path.join(project_folder, outfile.replace('.aup', '') + '_data')
if not os.path.isdir(datadir):
    os.mkdir(datadir)

# Update the directory paths for saving the .aup file and data
output_aup_path = os.path.join(project_folder, outfile)

# If we have a TGID CSV file, parse it into a dict
TGIDdict = {}
if TGID_CSV != '':
    with open(TGID_CSV, 'r') as f:
        for line in f:
            try:
                splitline = line.split(',')
                TGIDdict[int(splitline[0])] = splitline[3]
            except:
                pass

# Find relevant JSON files
fnames = []
min_timestamp = 2**64
for fname in os.listdir(rfilepath):
    if fname.endswith(".json"):
        timestamp = int(fname[fname.find("-")+1:fname.find("_")])
        TGID = fname[0:fname.find("-")]
        if TGID in TGIDS and timestamp > start_timestamp and timestamp < stop_timestamp:
            fnames.append(fname)
            if timestamp < min_timestamp:
                min_timestamp = timestamp
fnames.sort()

# Create the AUP XML file structure
data = ET.Element('project')
data.set('xmlns', 'http://audacity.sourceforge.net/xml')
data.set('projname', outfile.replace('.aup', '') + '_data')
data.set('version', '1.3.0')
data.set('audacityversion', '2.0.6')
data.set('rate', '8000')
tags = ET.SubElement(data, 'tags')

# Create a new WAV track for each TGID
for TGID in TGIDS:
    wavetrack = ET.SubElement(data, 'wavetrack')
    try:
        wavetrack.set('name', TGIDdict[int(TGID)])
    except:
        wavetrack.set('name', 'TG' + str(TGID))
    wavetrack.set('channel', '2')
    wavetrack.set('linked', '0')
    wavetrack.set('mute', '0')
    wavetrack.set('solo', '0')
    wavetrack.set('height', '100')
    wavetrack.set('minimized', '0')
    wavetrack.set('rate', '8000')
    wavetrack.set('gain', '1')
    wavetrack.set('pan', '0')

    # Create a new WAV clip for each transmission in the TGID
    for fname in fnames:
        timestamp = int(fname[fname.find("-")+1:fname.find("_")])
        if fname[0:fname.find("-")] == TGID:
            wavefilename = rfilepath + "/" + fname.replace('json', 'wav')
            with open(rfilepath + "/" + fname) as json_file:
                jdata = json.load(json_file)
            if args.splitwav == True and len(jdata['srcList']) > 1:
                i = 0
                srcList = jdata['srcList']
                for n, src in enumerate(srcList):
                    pos = float(src['pos'])
                    timestamp = int(src['time'])
                    aufilename = fname.replace('.json', '') + str(i) + '.au'
                    i += 1
                    if n == len(srcList) - 1:
                        nsamples, srate = convert_wav_to_au(wavefilename, datadir + '/' + aufilename, pos, None)
                    else:
                        nsamples, srate = convert_wav_to_au(wavefilename, datadir + '/' + aufilename, pos, float(srcList[n + 1]['pos']) - pos)
                    if nsamples <= 0:
                        os.remove(datadir + '/' + aufilename)
                    else:
                        waveclip = ET.SubElement(wavetrack, 'waveclip')
                        offset = timestamp - min_timestamp
                        waveclip.set('offset', str(offset))
                        envelope = ET.SubElement(waveclip, 'envelope')
                        envelope.set('numpoints', '0')
                        sequence = ET.SubElement(waveclip, 'sequence')
                        sequence.set('maxsamples', str(nsamples))
                        sequence.set('sampleformat', '262159')
                        sequence.set('numsamples', str(nsamples))
                        waveblock = ET.SubElement(sequence, 'waveblock')
                        waveblock.set('start', '0')
                        simpleblockfile = ET.SubElement(waveblock, 'simpleblockfile')
                        simpleblockfile.set('filename', aufilename)
                        simpleblockfile.set('len', str(nsamples))
            else:
                aufilename = fname.replace('.json', '') + '.au'
                nsamples, srate = convert_wav_to_au(wavefilename, datadir + '/' + aufilename, 0, None)
                waveclip = ET.SubElement(wavetrack, 'waveclip')
                offset = timestamp - min_timestamp
                waveclip.set('offset', str(offset))
                envelope = ET.SubElement(waveclip, 'envelope')
                envelope.set('numpoints', '0')
                sequence = ET.SubElement(waveclip, 'sequence')
                sequence.set('maxsamples', str(nsamples))
                sequence.set('sampleformat', '262159')
                sequence.set('numsamples', str(nsamples))
                waveblock = ET.SubElement(sequence, 'waveblock')
                waveblock.set('start', '0')
                simpleblockfile = ET.SubElement(waveblock, 'simpleblockfile')
                simpleblockfile.set('filename', aufilename)
                simpleblockfile.set('len', str(nsamples))

# Write the pretty-printed XML to the .aup file
pretty_xml_as_string = xml.dom.minidom.parseString(ET.tostring(data)).toprettyxml()
myfile = open(output_aup_path, "w")
myfile.write(pretty_xml_as_string)
myfile.close()

print(f"Audacity project created: {output_aup_path}")
