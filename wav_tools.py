# -*- coding: utf-8 -*-
"""
Copyright (C) 2016 Jonathan Taquet

This file is part of Oe2sSLE (Open e2sSample.all Library Editor).

Foobar is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Foobar is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Oe2sSLE.  If not, see <http://www.gnu.org/licenses/>
"""

import RIFF
import e2s_sample_all

import struct
import copy
import itertools
import sys

def wav_pcm_8b_to_16b(e2s_sample):
    # checks
    fmt = e2s_sample.get_fmt()
    if (   fmt.formatTag != fmt.WAVE_FORMAT_PCM
        or fmt.bitPerSample != 8):
        return None
    in_data = e2s_sample.get_data().rawdata
    n_samples = len(in_data)

    sample_values=struct.unpack(str(n_samples)+'B', in_data)
    w_sample_values=[(i - 128)*256 for i in sample_values]
    data=struct.pack('<'+str(n_samples)+'h',*w_sample_values)

    e2s_sample.get_chunk(b'data').data.rawdata = data
    e2s_sample.get_chunk(b'data').update_header()
    e2s_sample.update_header()
    fmt.bitPerSample = 16
    fmt.avgBytesPerSec *= 2
    fmt.blockAlign *= 2

    # TODO: update cue points chunkStart and blockStart if used later

    return e2s_sample

def wav_pcm_24b_to_16b(e2s_sample):
    # checks
    fmt = e2s_sample.get_fmt()
    if (   fmt.formatTag != fmt.WAVE_FORMAT_PCM
        or fmt.bitPerSample != 24):
        return None
    in_data=e2s_sample.get_data().rawdata
    n_samples = len(in_data)//3

    data=bytes([in_data[b] for i in range(n_samples) for b in (i*3+1, i*3+2)])

    e2s_sample.get_chunk(b'data').data.rawdata = data
    e2s_sample.get_chunk(b'data').update_header()
    e2s_sample.update_header()
    fmt.bitPerSample = 16
    fmt.avgBytesPerSec = fmt.avgBytesPerSec * 2 // 3
    fmt.blockAlign = fmt.blockAlign * 2 // 3

    # TODO: update cue points chunkStart and blockStart if used later

    return e2s_sample

"""
resample a too high frequency samples for playback preview
"""
import array
def wav_resample_preview(rawdata, fmt, max_smpl_per_sec):
    n_taps = 3
    freq = fmt.samplesPerSec
    data = array.array('h',rawdata)
    if fmt.formatTag != RIFF.WAVE_fmt_.WAVE_FORMAT_PCM:
        raise Exception('format tag')
    if fmt.bitPerSample != 16:
        raise Exception('bit per sample')
    if fmt.channels == 0:
        raise Exception('0 channels')
    if sys.byteorder == 'big':
        # wav file is little endian
        data.byteswap()
    n_chan = fmt.channels
    while int(freq) > max_smpl_per_sec:
        n_smpl = len(data)//n_chan
        wav = [data[chan::n_chan] for chan in range(n_chan)]
        if n_smpl%2 == 1:
            for chan in range(n_chan):
                wav[chan].extend([wav[chan][-1]]) # dublicate last sample to have a even number of sample
            n_smpl += 1
        data = array.array('h',(x for w in wav for x in ([(w[0]+w[1])//2] if n_smpl > 1 else []) + [(a+(b+c)//2)//2 for a, b, c in zip(w[2::2], w[1::2], w[3::2])] ))
        freq /= 2

    res_fmt = copy.deepcopy(fmt)
    res_fmt.samplesPerSec = int(freq)
    res_fmt.bytesPerSec = res_fmt.samplesPerSec*2*n_chan
    if sys.byteorder == 'big':
        # wav file is little endian
        data.byteswap()
    return (data.tobytes(), res_fmt)
