"""
Copyright (C) 2016-2017 Jonathan Taquet

This file is part of Oe2sSLE (Open e2sSample.all Library Editor).

Oe2sSLE is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Oe2sSLE is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Oe2sSLE.  If not, see <http://www.gnu.org/licenses/>
"""

import tkinter as tk
import tkinter.ttk

import copy

import audio
import e2s_sample_all
import GUI.res
import RIFF
import wav_tools

from GUI.wait_dialog import WaitDialog

class StereoToMonoDialog(tk.Toplevel):
    def __init__(self, parent, e2s_sample, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.transient(parent)
        self.title('Convert from stereo to mono ?')

        self.parent = parent
        self.e2s_sample = e2s_sample
        self.esli = e2s_sample_all.RIFF_korg_esli()
        self.esli.rawdata[:] = e2s_sample.get_esli().rawdata[:]
        prev_fmt = e2s_sample.get_fmt()
        self.fmt = copy.deepcopy(prev_fmt)
        self.fmt.channels=1
        self.fmt.avgBytesPerSec = self.fmt.avgBytesPerSec // prev_fmt.channels
        self.fmt.blockAlign = self.fmt.blockAlign // prev_fmt.channels
        self.esli.OSC_StartPoint_address = self.esli.OSC_StartPoint_address // prev_fmt.channels
        self.esli.OSC_LoopStartPoint_offset = self.esli.OSC_LoopStartPoint_offset // prev_fmt.channels
        self.esli.OSC_EndPoint_offset = self.esli.OSC_EndPoint_offset // prev_fmt.channels
        self.esli.WAV_dataSize = self.esli.WAV_dataSize // prev_fmt.channels
        self.esli.useChan1 = False
        self.w = (0,0)
        self.data = None
        self.result = None

        self.mix_var = tk.DoubleVar()

        tk.Label(self, text="Stereo to mono mix settings").pack(fill=tk.X)
        body = tk.Frame(self)

        tk.Label(body, text="L").pack(side=tk.LEFT)
        self.mix_scale = tk.Scale(body, variable = self.mix_var, orient=tk.HORIZONTAL, from_=-1, to=1, resolution=0.001)
        self.mix_scale.pack(fill=tk.X, side=tk.LEFT, expand=True)
        tk.Label(body, text="R").pack(side=tk.LEFT)
        self.buttonPlay = tk.Button(body, image=GUI.res.playIcon, command=self.play)
        self.buttonPlay.pack(side=tk.LEFT, padx=5, pady=5)
        self.buttonStop = tk.Button(body, image=GUI.res.stopIcon, command=self.stop)
        self.buttonStop.pack(side=tk.LEFT, padx=5, pady=5)
        #self.waitBar = tk.ttk.Progressbar(body, orient='horizontal', mode='indeterminate', length=320)
        #self.waitBar.pack(expand=True, fill=tk.BOTH, side=tk.TOP)
        #self.waitBar.start()
        body.pack(fill=tk.BOTH, expand=True)#(padx=5, pady=5)
        
        box = tk.Frame(self)
        
        w = tk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE)
        w.pack(side=tk.LEFT, padx=5, pady=5)
        w = tk.Button(box, text="Cancel", width=10, command=self.cancel)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        self.bind("<space>", lambda event: self.play())

        box.pack()

#        self.protocol("WM_DELETE_WINDOW", self.close)

#        self.waitBar.focus_set()
        self.mix_scale.focus_set()

        # temporarily hide the window
        self.withdraw()
        self.update()
        width, height = (self.winfo_width(), self.winfo_height())
        self.minsize(width, height)
        px, py = (parent.winfo_rootx(), parent.winfo_rooty())
        pwidth, pheight = (parent.winfo_width(), parent.winfo_height())
        x, y = (px+pwidth/2-width/2, py+pheight/2-height/2)
        self.geometry("+{}+{}".format(int(x), int(y)))
        self.deiconify()
        self.grab_set()

    def update_data(self):
        num_chans = self.e2s_sample.get_fmt().channels
        if num_chans == 1:
            if self.data is None:
                self.data=self.e2s_sample.get_data().rawdata
        else:
            mix = self.mix_var.get()
            w = ((1 - mix)/2, 1 - (1 - mix)/2) + (0,)*(num_chans-2)
            if self.w != (w):
                self.w=w
                wav = wav_tools.wav_from_raw16b(self.e2s_sample.get_data().rawdata, num_chans)
                n_smpl = len(wav[0])
                def action():
                    def cb(step):
                        wd.waitBar.step(step)
                    step = 4096
                    self.data=wav_tools.raw16b_from_wav(wav_tools.wav_mchan_to_mono(wav, self.w, cb, step))
                wd = WaitDialog(self.parent)
                wd.run_max(action, n_smpl)

    def play(self):
        self.stop()
        self.update_data()
        audio.player.play_start(audio.LoopWaveSource(self.data,self.fmt,self.esli))

    def stop(self):
        audio.player.play_stop()

    #
    # standard button semantics

    def ok(self, event=None):
        self.withdraw()
        self.update_idletasks()

        self.apply()

        self.cancel()

    def cancel(self, event=None):
        self.stop()
        # put focus back to the parent window
        self.parent.focus_set()
        self.destroy()

    def apply(self):
        self.update_data()
        esli_chunk = self.e2s_sample.get_esli().rawdata = self.esli.rawdata
        fmt__chunk = self.e2s_sample.get_fmt().__dict__ = self.fmt.__dict__
        data_chunk = self.e2s_sample.get_data().rawdata = self.data
