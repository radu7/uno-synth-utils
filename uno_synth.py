#!/usr/bin/python
#
# Script decode/encode configuration files for the IK UNO Synth
# (c) Simon Wood, 18 June 2019
#

import sys
import os
import time
from optparse import OptionParser
from construct import *

#--------------------------------------------------
# For Midi capabilites (optional)

global inport
global outport

try:
    import mido
    _hasMido = True
    if sys.platform == 'win32':
        mido.set_backend('mido.backends.rtmidi_python')
except ImportError:
    _hasMido = False
'''
_hasMido = False
'''

#--------------------------------------------------
# Define file format using Construct (v2.9)
# requires:
# https://github.com/construct/construct

Oscillator = Struct(
    "wave" / Short,
    "skip" / Bytes(2),
    "tune" / Short,
    "skip" / Bytes(2),
    "level" / Byte,
    "skip" / Bytes(2),
    )

ADSR = Struct(
    "attack" / Short,
    "skip" / Bytes(2),
    "delay" / Short,
    "skip" / Bytes(2),
    "sustain" / Short,
    "skip" / Bytes(1),
    "release" / Short,
    "skip" / Bytes(2),
    )

Config = Struct(
    "skip" / Bytes(7),
    "tempo" / Short,
    "skip" / Bytes(2),
    "octave" / Byte,
    "skip" / Bytes(2),
    "glide" / Byte,
    "skip" / Bytes(3),
    "scale" / Byte,
    "skip" / Bytes(5),
    "delay_time" / Byte,
    "skip" / Bytes(2),
    "delay_mix" / Byte,
    "skip" / Bytes(2),
    "arp_direction" / Byte,
    "skip" / Bytes(5),
    "seq_direction" / Byte,
    "skip" / Bytes(2),
    "range" / Byte,
    "skip" / Bytes(2),

    "oscillator1" / Oscillator,
    "oscillator2" / Oscillator,

    "noise_level" / Byte,

    "skip" / Bytes(2),
    "filter_cutoff" / Short,
    "skip" / Bytes(2),
    "filter_mode" / Byte,
    "skip" / Bytes(2),
    "filter_res" / Byte,
    "skip" / Bytes(2),
    "filter_drive" / Short,
    "skip" / Bytes(1),
    "filter_env_amount" / Short,
    "skip" / Bytes(2),

    "filter" / ADSR,
    "envelope" / ADSR,

    "lfo_wave" / Byte,
    "skip" / Bytes(2),
    "lfo_rate" / Short,
    "skip" / Bytes(2),
    "lfo_pitch" / Short,
    "skip" / Bytes(2),
    "lfo_filter" / Short,

    "skip98" / Bytes(86),
    "skip99" / Bytes(7),
    )

Seq = Struct(
    "step" / Byte,
    "count" /Byte,

    "elements" / Array(this.count, Struct(
        "type" / Enum(Byte,
            SEQ00 = 0,
            SEQ16 = 16,
            PARAM = 32,
            SEQ48 = 48,
            NOTE = 64,
        ),

        "element" / Switch(this.type,
        {
           "SEQ00" : "Seq00" / Struct(
                "param" / Enum(Byte,
                    LEVEL1 = 15,
                    LEVEL2 = 18,
                    NOISE = 19,

                    MODE = 0,       # not sequencible?
                    RES = 22,
                    DRIVE = 23,
                    ENV_AMT = 24,

                    DELAY_T = 7,
                    DELAY_M = 8,

                ),
                "par2" / Byte,
            ),
            "SEQ16" : "Seq16" / Struct(	# seen in 'PLUCK Castle Time'
                "par1" / Byte,
                "par2" / Byte,
            ),
            "PARAM" : "SeqParam" / Struct(
                "param" / Enum(Byte,
                    WAVE1 = 13,
                    WAVE2 = 16,
                    TUNE1 = 14,
                    TUNE2 = 17,

                    FIL_A = 25,
                    FIL_D = 26,
                    FIL_S = 27,
                    FIL_R = 28,

                    ENC_A = 29,
                    ENC_D = 30,
                    ENC_S = 31,
                    ENC_R = 32,

                    LFO_WAVE = 0,       # not sequencible?
                    LFO_RATE = 0,       # not sequencible?
                    LFO_PITCH = 35,
                    LFO_FILTER = 36,

                    CUTOFF = 20,
                    GLIDE = 4,
                ),
                "before" / Byte,
                "after" / Byte,
            ),
            "SEQ48" : "Seq48" / Struct(
                "param" / Enum(Byte,
                    VAL_4 = 4,          # '0xb0441c'
                    VAL_20 = 20,        # '0xb0141b'
                    VAL_24 = 24,        # Sends CC '0xb01723' -> 'Filter Env Amount'?
                    VAL_25 = 25,
                    VAL_35 = 35,
                ),
                "val_hi" / Byte,        # 16bit signed
                "val_lo" / Byte,
            ),
            "NOTE" : "SeqNote" / Struct(
                Const(b"\x00"),
                "note" /Byte,
                "vel" / Byte,
                "len" / Byte,
                Const(b"\x00"),
            ),
        },
        default = Pass),
    )),
)

Uno = Sequence(
    Config,
    GreedyRange(Seq),
)

#--------------------------------------------------


def main():
    global config

    data = None
    inport = None
    outport = None

    usage = "usage: %prog [options] FILENAME"
    parser = OptionParser(usage)
    parser.add_option("-v", "--verbose",
        action="store_true", dest="verbose")
    parser.add_option("-d", "--dump",
        help="dump configuration/sequence to text",
        action="store_true", dest="dump")

    if _hasMido:
        parser.add_option("-m", "--midi", dest="midi", default="UNO Synth",
            help="Select 'MIDI' device name")
        parser.add_option("-p", "--preset", dest="preset",
            help="Select 'PRESET' and use in MIDI operations" )
        parser.add_option("-r", "--read", dest="read",
            help="Read current (or 'PRESET') config from UNO",
            action="store_true")
        parser.add_option("-w", "--write", dest="write",
            help="Read write config to 'PRESET' on attached UNO",
            action="store_true")
        parser.add_option("-B", "--backup", dest="backup",
            help="Backup all presets (21-100) from UNO to 'BACKUP' directory")

    (options, args) = parser.parse_args()

    if _hasMido:
        if options.preset or options.read or options.write or options.backup:
            if sys.platform == 'win32':
                name = bytes(options.midi, 'ascii')
            else:
                name = options.midi
            for port in mido.get_input_names():
                if port[:len(name)]==name:
                    inport = mido.open_input(port)
                    break
            for port in mido.get_output_names():
                if port[:len(name)]==name:
                    outport = mido.open_output(port)
                    break
            if inport == None or outport == None:
                sys.exit("Midi: Unable to find UNO Synth")

        if options.read or options.preset:
            if options.preset and int(options.preset) <= 100:
                # Switch UNO to preset
                data=(0x00,0x21,0x1a,0x02,0x01,0x33,int(options.preset))
                msg = mido.Message('sysex', data=data)
                outport.send(msg)

            if options.read:
                # Read config from UNO
                data=(0x00,0x21,0x1a,0x02,0x01,0x31)
                msg = mido.Message('sysex', data=data)
                outport.send(msg)
                for msg in inport:
                    if msg.type=='sysex':
                        if len(msg.data) > 229 and msg.data[6]==0x31:
                            data = bytes(msg.data[10:])
                            break

        if options.backup:
            path = os.path.join(os.getcwd(), options.backup)
            os.mkdir(path)

            for preset in range(21,101,1):
                data=(0x00,0x21,0x1a,0x02,0x01,0x33,preset)
                msg = mido.Message('sysex', data=data)
                outport.send(msg)

                # temp hack to allow UNO time to switch
                time.sleep(1)

                name = os.path.join(path, str(preset) + ".unosyp")
                outfile = open(name, "wb")
                if not outfile:
                    sys.exit("Unable to open config FILE for writing")

                data=(0x00,0x21,0x1a,0x02,0x01,0x31)
                msg = mido.Message('sysex', data=data)
                outport.send(msg)
                for msg in inport:
                    if msg.type=='sysex':
                        if len(msg.data) > 229 and msg.data[6]==0x31:
                            data = bytes(msg.data[10:])
                            break

                outfile.write(data)
                outfile.close()


    # check whether we've already got data
    if data == None:
        if len(args) != 1:
            parser.error("config FILE not specified")

        if options.verbose:
            print("Reading %s..." % args[0])

        infile = open(args[0], "rb")
        if not infile:
            sys.exit("Unable to open config FILE for reading")

        data = infile.read(2000)
        infile.close()

    if options.dump and data:
        config = Uno.parse(data)
        print(config)

    # When reading from UNO, write data to file.
    if _hasMido:
        if options.read and data and len(args) == 1:
            outfile = open(args[0], "wb")
            if not outfile:
                sys.exit("Unable to open config FILE for writing")

            outfile.write(data)
            outfile.close()


if __name__ == "__main__":
    main()

