# -*- coding: utf-8 -*-
"""
Copyright (C) 2015-2017 Jonathan Taquet

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
import tkinter.filedialog
import tkinter.messagebox
import tkinter.ttk
#import re
import math
import platform
#import time
import sys

import RIFF
import e2s_sample_all as e2s
from VerticalScrolledFrame import VerticalScrolledFrame

import os
import os.path

import audio

import struct
import webbrowser

from GUI.widgets import ROCombobox
from GUI.widgets import ROSpinbox
import GUI.res
from GUI.stereo_to_mono import StereoToMonoDialog
from GUI.wait_dialog import WaitDialog
from GUI.about_dialog import AboutDialog
from GUI.import_options import ImportOptionsDialog, ImportOptions
from GUI.export_options import ExportOptionsDialog, ExportOptions
from GUI.exchange_sample_dialog import ExchangeSampleDialog
from GUI.tooltip import ToolTip

import e2s_sample_import

import utils

from version import Oe2sSLE_VERSION, debug

Oe2sSLE_dir = os.path.expanduser('~') + os.sep + '.Oe2sSLE'

if not debug:
    class logger:

        log_file_path = Oe2sSLE_dir + os.sep + 'Oe2sSLE.log'

        def __init__(self):
            self.file = None
            self.stderr = sys.stderr
            self.stdout = sys.stdout
            sys.stderr=self
            sys.stdout=self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            if self.file:
                self.file.write('-- Logger closed --\n')
                self.file.close()
            sys.stderr = self.stderr
            sys.stdout = self.stdout

        def write(self, data):
            try:
                if not self.file:
                    if not os.path.exists(Oe2sSLE_dir):
                        os.makedirs(Oe2sSLE_dir)
                    self.file = open(self.log_file_path, 'a')
                self.file.write(data)
                self.file.flush()
            except BaseException as e:
                tk.messagebox.showerror(
                    "Critical Error",
                    (
                        'Failed to write in log file {}:\n'
                        'Error: {}\n'
                        'This occured while trying to log following message:\n'
                        '{}'
                    ).format(self.log_file_path, e, data)
                )
else:
    class logger:
        def __init__(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_value, traceback):
            pass

def linspace(start,stop,num):
    for i in range(num):
        yield start+((stop-start)*i)/(num-1)

class WaveDisplay(tk.Canvas):
    class LineSet:
        def __init__(self, first, last, loop_first=None, attack_last=None, amplitude=None):
            self.first=first
            self.last=last
            self.loop_first=loop_first
            self.attack_last=attack_last
            self.amplitude=amplitude
    
    def __init__(self, *arg, **kwarg):
        kwarg['highlightthickness']=0
        super().__init__(*arg, **kwarg)
        self.bind("<Configure>", self.on_resize)
        self.height = self.winfo_reqheight()
        self.width = self.winfo_reqwidth()
        
        self.toRefresh = False
        self.refreshLineSetOnly = False
        self.scrollBar = None

        self.wav = [[int(20000*math.sin(x*2.*math.pi/self.width)) for x in range(self.width)]]*2
        self.bitmap = bytearray()
        self.dispFrom = 0
        self.dispTo = self.width-1
        
        self.ampMax = 32767
        self.ampTot = 65536
        self.bgColor = (0,0,127)
        self.wavColor= (0,0,255)
        self.photo = tk.PhotoImage(width=self.width, height=self.height)
        self.photo_handle = self.create_image((0,0), anchor=tk.NW, image=self.photo, state="normal")

        self.refresh()

        self.lineSets = []
        self.activeLineSet = None

        self.bind("<Motion>", self.on_motion)
        self.bind("<ButtonPress-1>", self.on_b1_press)
        self.bind("<ButtonRelease-1>", self.on_b1_release)
        self.bind("<B1-Motion>", self.on_b1_motion)
        
    def set_activeLineSet(self, activeLineSet=None):
        if self.activeLineSet != activeLineSet:
            self.activeLineSet=activeLineSet
            self.refresh(True)
    
    def add_lineSet(self, lineSet):
        self.lineSets.append(lineSet)
        self.refresh(True)

    def set_scrollBar(self, scrollBar):
        self.scrollBar = scrollBar
        self.update_scrollBar()

    def set_wav(self, wave_fmt, wave_data):
        if wave_fmt.formatTag != RIFF.WAVE_fmt_.WAVE_FORMAT_PCM:
            raise Exception('format tag')
        if wave_fmt.bitPerSample != 16:
            raise Exception('bit per sample')
        num_chans = wave_fmt.channels
        num_samples = len(wave_data.rawdata)//2//num_chans
        tot_num_samples = num_samples*num_chans
        samples = struct.unpack('<'+str(tot_num_samples)+'h', wave_data.rawdata)
        self.wav = []
        for chan in range(num_chans):
            self.wav.append(samples[chan:tot_num_samples:num_chans])
        self.dispFrom = 0
        self.dispTo = num_samples
        self.activeLineSet = None
        self.refresh()
        
    def wav_length(self):
        return len(self.wav[0])
    
    def num_channels(self):
        return len(self.wav)

    def set_disp(self, dispFrom, dispTo):
        assert dispFrom < dispTo
        if dispFrom != self.dispFrom or dispTo != self.dispTo:
            self.dispFrom = dispFrom
            self.dispTo = dispTo
            self.refresh()
            
    def display_sample(self, index):
        if index < self.dispFrom:
            self.set_disp(index, self.dispTo - self.dispFrom + index)
        elif index > self.dispTo:
            self.set_disp(self.dispFrom - self.dispTo + index, index)
    
    """
    scroll by a step in samples
    """
    def scroll(self, step):
        self.set_disp(self.dispFrom+step, self.dispTo+step)
    
    def scroll_to(self, offset):
        self.scroll(offset - self.dispFrom)

    def scroll_stop(self, step):
        if step < 0:
            if self.dispFrom >= 0:
                step = max(step, -self.dispFrom)
            else:
                step = 0
        elif step > 0:
            if self.dispTo <= self.wav_length()-1:
                step = min(step, self.wav_length()-self.dispTo)
            else:
                step = 0
        self.scroll(step)
        
    """
    scroll by a step equvalent to pixels
    """
    def scroll_pix(self, step):
        self.scroll(step/self.get_zoom_x())

    def scroll_pix_stop(self, step):
        self.scroll_stop(step/self.get_zoom_x())

    def set_zoom_x(self, zoom):
        x_mid = self.dispFrom + (self.dispTo-self.dispFrom)/2
        dispFrom = int(round(x_mid-self.width/zoom/2))
        dispTo = int(round(x_mid+self.width/zoom/2))
        if dispFrom < -1:
            diff = -1-dispFrom
            dispFrom += diff
            dispTo += diff
        if dispTo > self.wav_length()-1:
            dispTo=self.wav_length()-1
        self.set_disp(dispFrom,dispTo)
        
    def get_zoom_x(self):
        return self.width/(self.dispTo-self.dispFrom)
        
    def wav_view_length(self):
        return self.dispTo-self.dispFrom
    
    """
    """
    def on_motion(self,event):
        lineset = self.activeLineSet
        if lineset is not None:
            amp_active = 1 #lineset.loop_first is None
        
            if (abs(event.x-lineset._last_x) < 5
                or abs(event.x-lineset._mid_x) < 5
                or abs(event.x-lineset._first_x) < 5):
                if self.cget('cursor') != 'sb_h_double_arrow':
                    self.configure(cursor='sb_h_double_arrow')
            elif (amp_active
                and (abs(event.y-lineset._amp_y0) < 5
                    or abs(event.y-lineset._amp_y1) < 5)
                and event.x >= lineset._amp_start_x
                and event.x <= lineset._amp_end_x):
                if self.cget('cursor') != 'sb_v_double_arrow':
                    self.configure(cursor='sb_v_double_arrow')
            else:
                if self.cget('cursor'):
                    self.configure(cursor='')

    def on_b1_press(self,event):
        self.drag=0
        lineset = self.activeLineSet
        if lineset is not None:
            amp_active = 1 #lineset.loop_first is None
        
            if abs(event.x-lineset._last_x) < 5:
                self.drag=3
            elif abs(event.x-lineset._mid_x) < 5:
                self.drag=2
            elif abs(event.x-lineset._first_x) < 5:
                self.drag=1
            elif amp_active:
                if abs(event.y-lineset._amp_y1) < 5:
                    self.drag=5
                elif abs(event.y-lineset._amp_y0) < 5:
                    self.drag=4

    def on_b1_release(self,event):
        self.drag=0

    def on_b1_motion(self,event):
        if self.drag:
            lineset = self.activeLineSet

            x = event.x
            y = event.y
            
            w = self.width
            h = self.height
            fr = self.dispFrom
            to = self.dispTo
            num_chans = self.num_channels()

            if self.drag < 4:
                new_x=int(fr+x*(to-fr)/w)
                if self.drag == 1:
                    lineset.first.set(new_x)
                elif self.drag == 2:
                    if lineset.loop_first is not None:
                        lineset.loop_first.set(new_x)
                    else:
                        lineset.attack_last.set(new_x)
                elif self.drag == 3:
                    lineset.last.set(new_x)
            else:
                if self.drag == 4:
                    new_y=int(self.ampTot-y*num_chans*self.ampTot*2/h)
                    lineset.amplitude.set(abs(new_y))
                elif self.drag == 5:
                    new_y=int(y*num_chans*self.ampTot*2/h-self.ampTot)
                    lineset.amplitude.set(abs(new_y))

    def on_resize(self,event):
        if self.width == event.width and self.height == event.height:
            return
        self.width = event.width
        self.height = event.height
        self.refresh()
        
    def refresh(self, line_set_only=False):
        if self.refreshLineSetOnly and not line_set_only:
            self.refreshLineSetOnly = False
        if not self.toRefresh:
            self.toRefresh=True
            self.after_idle(self.draw_wav)
        self.update_scrollBar()

    def update_scrollBar(self):
        if self.scrollBar:
            self.scrollBar.set(self.dispFrom/self.wav_length(), self.dispTo/self.wav_length())

    def draw_wav(self):
        # TODO:
        #  - put image into object
        #  - allow to update only parts : slice bar drawn, ...
        #while True:
        if self.toRefresh:
            self.toRefresh=False
            w = self.width
            h = self.height
            fr = self.dispFrom
            to = self.dispTo
    
            wstep = w*3
            
            # from python 3.5:
            #header = b"P6 %d %d 255 " % (w, h)
            header = bytes("P6 %d %d 255 " % (w, h), "utf8")
            head_l = len(header)

            if self.wav:
                num_chans = self.num_channels()

            if not self.refreshLineSetOnly:
                self.refreshLineSetOnly = True
                self.wav_ppm = bytearray(head_l+w*h*3)
                ppm = self.wav_ppm
                ppm[0:head_l] = header
                # init with bg color
                ppm[head_l:] = self.bgColor*(w*h)
                # draw zero line(s)
                if self.wav:
                    for chan in range(num_chans):
                        line=int((self.ampMax/self.ampTot+chan)*(h/num_chans))
                        ppm[head_l+line*wstep:head_l+(line+1)*wstep] = (127,127,127)*w
            
                # draw wav
                if self.wav:
                    for chan in range(num_chans):
                        _smin=0
                        _smax=0
                        for x in range(w):
                            start=max(0,int(fr+math.floor((to-fr)*(x)/w)))
                            stop=min(self.wav_length(),max(start+1,int(fr+math.floor((to-fr)*(x+1.)/w))))
                            if stop>start:
                                __smin=min(self.wav[chan][start:stop])
                                __smax=max(self.wav[chan][start:stop])
                                smin=min(_smax,__smin)
                                smax=max(_smin,__smax)
                                _smin=__smin
                                _smax=__smax
                            
                                pStart=int(((self.ampMax-smax)/self.ampTot+chan)*(h/num_chans))
                                pStop =int(((self.ampMax-smin)/self.ampTot+chan)*(h/num_chans))+1

                                #for i in range(pStop-pStart):
                                #    ppm[head_l+x*3+wstep*(i+pStart)+0:head_l+x*3+wstep*(i+pStart)+3] = self.wavColor
                                ppm[head_l+x*3+wstep*pStart+0:head_l+x*3+wstep*pStop+0:wstep] = (self.wavColor[0],)*(pStop-pStart)
                                ppm[head_l+x*3+wstep*pStart+1:head_l+x*3+wstep*pStop+1:wstep] = (self.wavColor[1],)*(pStop-pStart)
                                ppm[head_l+x*3+wstep*pStart+2:head_l+x*3+wstep*pStop+2:wstep] = (self.wavColor[2],)*(pStop-pStart)                    

            # draw line sets
            ppm = bytearray(head_l+w*h*3)
            ppm[:] = self.wav_ppm
            for active in (False, True):
                for lineSet in self.lineSets:
                    if active == (lineSet is self.activeLineSet):
                        first = lineSet.first.get()
                        last = lineSet.last.get()
                        if lineSet.loop_first is not None:
                            mid = lineSet.loop_first.get()
                        else:
                            mid = lineSet.attack_last.get()
                        amp = lineSet.amplitude.get()
                        if amp is not None:
                            start_x = max(0, math.floor((first+0.25 - fr)*w/(to - fr)))
                            end_x = min(w-1, math.ceil((last+0.75 - fr)*w/(to - fr)))

                            if active:
                                lineSet._amp_start_x = start_x
                                lineSet._amp_end_x = end_x
                                lineSet._amp_y0 = max(0,int((math.floor((self.ampTot-amp)/2)/self.ampTot)*(h/num_chans)))
                                lineSet._amp_y1 = min(h-1,int((math.floor((self.ampTot+amp)/2)/self.ampTot)*(h/num_chans)))
                            
                            
                            if end_x > start_x:
                                for chan in range(num_chans):
                                    y0 = max(0,int((math.floor((self.ampTot-amp)/2)/self.ampTot+chan)*(h/num_chans)))
                                    y1 = min(h-1,int((math.floor((self.ampTot+amp)/2)/self.ampTot+chan)*(h/num_chans)))
                                    if active:
                                        ppm[head_l+start_x*3+wstep*y0+0:head_l+(end_x+1)*3+wstep*y0+0:3] = (255,)*(end_x-start_x+1)
                                        ppm[head_l+start_x*3+wstep*y1+0:head_l+(end_x+1)*3+wstep*y1+0:3] = (255,)*(end_x-start_x+1)
                                    else:
                                        ppm[head_l+start_x*3+wstep*y0+0:head_l+(end_x+1)*3+wstep*y0+0:3] = (127,)*(end_x-start_x+1)
                                        ppm[head_l+start_x*3+wstep*y0+1:head_l+(end_x+1)*3+wstep*y0+1:3] = (127,)*(end_x-start_x+1)
                                        ppm[head_l+start_x*3+wstep*y1+0:head_l+(end_x+1)*3+wstep*y1+0:3] = (127,)*(end_x-start_x+1)
                                        ppm[head_l+start_x*3+wstep*y1+1:head_l+(end_x+1)*3+wstep*y1+1:3] = (127,)*(end_x-start_x+1)

                        if fr <= mid <= to:
                            x = round((mid+0.5 - fr)*w/(to - fr))
                            if x >= w:
                                x = w-1
                            # some green
                            if active:
                                ppm[head_l+x*3+1:head_l+x*3+wstep*h+1:wstep] = (255,)*h
                                lineSet._mid_x=x
                            else:
                                ppm[head_l+x*3+1:head_l+x*3+wstep*h+1:wstep] = (127,)*h
                        elif active:
                            lineSet._mid_x=round((mid+0.5 - fr)*w/(to - fr))
                                
                        if fr <= first <= to:
                            x = math.floor((first+0.25 - fr)*w/(to - fr))
                            # some green and red
                            if active:
                                ppm[head_l+x*3+0:head_l+x*3+wstep*h+0:wstep] = (255,)*h
                                ppm[head_l+x*3+1:head_l+x*3+wstep*h+1:wstep] = (255,)*h
                                lineSet._first_x=x
                            else:
                                ppm[head_l+x*3+0:head_l+x*3+wstep*h+0:wstep] = (127,)*h
                                ppm[head_l+x*3+1:head_l+x*3+wstep*h+1:wstep] = (127,)*h
                        elif active:
                            lineSet._first_x=math.floor((first+0.25 - fr)*w/(to - fr))
                        
                        if fr <= last <= to:
                            x = math.ceil((last+0.75 - fr)*w/(to - fr))
                            if x >= w:
                                x = w-1
                            # some red
                            if active:
                                ppm[head_l+x*3+0:head_l+x*3+wstep*h+0:wstep] = (255,)*h
                                lineSet._last_x=x
                            else:
                                ppm[head_l+x*3+0:head_l+x*3+wstep*h+0:wstep] = (127,)*h
                        elif active:
                            lineSet._last_x=math.ceil((last+0.75 - fr)*w/(to - fr))
                
            self.photo.configure(data=bytes(ppm), width=w, height=h)

class MaxValueEntry(tk.Entry):
    def __init__(self, parent, max, *arg, **kwarg):
        self.MVEmax = max
        self.MVEvar = kwarg.get('textvariable')
        if self.MVEvar:
            self.MVEvar_trace = self.MVEvar.trace('w', self._var_set)
        super().__init__(parent, *arg, **kwarg)
        self.defaultbg =  self.cget('disabledbackground')

    def config(self, *arg, **kwarg):
        var = kwarg.get('textvariable')
        if var:
            if self.MVEvar:
                self.MVEvar.trace_vdelete('w', self.MVEvar_trace)
            self.MVEvar=var
        super().config(*arg, **kwarg)
        if var:
            self.MVEvar_trace = self.MVEvar.trace('w', self._var_set)

    def _var_set(self, *args):
        val = self.MVEvar.get()
        if val <= self.MVEmax:
            self.config(disabledbackground=self.defaultbg)
        else:
            self.config(disabledbackground="#C80000")


class SampleNumSpinbox(ROSpinbox):
    def __init__(self, parent, *arg, **kwarg):
        self.SNScommand=kwarg.get('command')
        self.SNSvar=kwarg.get('textvariable')
        if self.SNSvar:
            self.SNSvarString=tk.StringVar()
            self.SNSvarString.set(self.SNSvar.get())
            kwarg['textvariable'] = self.SNSvarString
        super().__init__(parent, *arg, **kwarg)
        self.config(state=tk.NORMAL)
        self.defaultbg =  self.cget('background')
        
        self.bind("<Shift-Up>",lambda event: self.big_increase(98))
        self.bind("<Shift-Down>",lambda event: self.big_increase(-98))
        self.bind("<Prior>",lambda event: self.big_increase(999))
        self.bind("<Next>",lambda event: self.big_increase(-999))
        self.bind("<Shift-Prior>",lambda event: self.big_increase(9999))
        self.bind("<Shift-Next>",lambda event: self.big_increase(-9999))

        if self.SNSvar:
            self._safeSet=False
            self.SNSvar_trace = self.SNSvar.trace('w', self._var_set)
            self.SNSvarString_trace = self.SNSvarString.trace('w', self._varString_set)

    def config(self, *arg, **kwarg):
        command=kwarg.get('command')
        if command:
            self.SNScommand = command
        var=kwarg.get('textvariable','')
        if var != '':
            if self.SNSvar:
                self.SNSvar.trace_vdelete('w', self.SNSvar_trace)
                self.SNSvarString.trace_vdelete('w', self.SNSvarString_trace)
            self.SNSvar=var
            if var:
                self.SNSvarString=tk.StringVar()
                self.SNSvarString.set(self.SNSvar.get())
                kwarg['textvariable'] = self.SNSvarString
        super().config(*arg, **kwarg)
        if var:
            self._safeSet=False
            self.SNSvar_trace = self.SNSvar.trace('w', self._var_set)
            self.SNSvarString_trace = self.SNSvarString.trace('w', self._varString_set)

    def _var_set(self, *args):
        if not self._safeSet:
            self.SNSvarString.set(self.SNSvar.get())

    def _varString_set(self, *args):
        v=self.SNSvarString.get()
        _max=int(self.cget('to'))
        _min=int(self.cget('from'))
        if utils.isint(v) and _min <= int(v) <= _max:
            self.config(background=self.defaultbg)
            self._safeSet=True
            self.SNSvar.set(v)
            self._safeSet=False
            # execute the command
            if self.SNScommand:
                self.SNScommand()
        else:
            self.config(background="#C80000")


    def big_increase(self, increment):
        _curr=int(self.get())
        _max=int(self.cget('to'))
        _min=int(self.cget('from'))
        _next=min(_curr+increment,_max)
        _next=max(_next,_min)
        self.tk.globalsetvar(self.cget('textvariable'),_next)
        if increment:
            self.invoke('buttonup' if increment > 0 else 'buttondown')

class CVar:
    def __init__(self, var, min, max):
        self.var = var
        self.min = min
        self.max = max
        
    def set(self, value):
        if value < self.min:
            self.var.set(self.min)
        elif value > self.max:
            self.var.set(self.max)
        else:
            self.var.set(value)
            
    def get(self):
        return self.var.get()

class Slice:
    def __init__(self, master, editor, sliceNum):
        self.master = master
        self.editor = editor
        self.sliceNum = sliceNum
        
        self.labelSlice = tk.Label(self.master, text="Slice "+str(self.sliceNum)).grid(row=sliceNum+1)

        self.start  = tk.IntVar()
        self.stop = tk.IntVar()
        self.attack = tk.IntVar()
        self.amplitude = tk.IntVar()
        
        self.startTrace = None
        self.stopTrace = None
        self.attackTrace = None
        self.amplitudeTrace = None

        self.entryStart = SampleNumSpinbox(self.master, width=10, from_=0, textvariable=self.start, state='readonly')
        self.entryStop = SampleNumSpinbox(self.master, width=10, from_=-1, textvariable=self.stop, state='readonly')
        self.entryAttack = SampleNumSpinbox(self.master, width=10, from_=-1, textvariable=self.attack, state='readonly')
        self.entryAmplitude = SampleNumSpinbox(self.master, width=10, from_=0, textvariable=self.amplitude, state='readonly')
        self.buttonPlay = tk.Button(self.master, image=GUI.res.playIcon, command=self._play)
        
        self._selected=False
        self.entryStart.bind("<FocusIn>",self._focus_in,add="+")
        self.entryStart.bind("<FocusOut>",self._focus_out,add="+")
        self.entryStop.bind("<FocusIn>",self._focus_in,add="+")
        self.entryStop.bind("<FocusOut>",self._focus_out,add="+")
        self.entryAttack.bind("<FocusIn>",self._focus_in,add="+")
        self.entryAttack.bind("<FocusOut>",self._focus_out,add="+")
        self.entryAmplitude.bind("<FocusIn>",self._focus_in,add="+")
        self.entryAmplitude.bind("<FocusOut>",self._focus_out,add="+")

        self.entryStart.grid(row=sliceNum+1, column=1)
        self.entryStop.grid(row=sliceNum+1, column=2)
        self.entryAttack.grid(row=sliceNum+1, column=3)
        self.entryAmplitude.grid(row=sliceNum+1, column=4)
        self.buttonPlay.grid(row=sliceNum+1, column=5)
        
        self.lineSet = WaveDisplay.LineSet(self.start,self.stop,attack_last=self.attack,amplitude=self.amplitude)
        self.editor.wavDisplay.add_lineSet(self.lineSet)

    def set_sample(self, fmt, data, esli):
        if self.startTrace:
            self.start.trace_vdelete('w', self.startTrace)
        if self.stopTrace:
            self.stop.trace_vdelete('w', self.stopTrace)
        if self.attackTrace:
            self.attack.trace_vdelete('w', self.attackTrace)
        if self.amplitudeTrace:
            self.amplitude.trace_vdelete('w', self.amplitudeTrace)

        self.fmt = fmt
        self.data = data.rawdata
        self.esli = esli
        
        self.blockAlign = fmt.blockAlign
        self.sample_length = len(data) // self.blockAlign

        start=esli.slices[self.sliceNum].start + self.esli.OSC_StartPoint_address//self.blockAlign
        stop=start+esli.slices[self.sliceNum].length-1
        attack=start+esli.slices[self.sliceNum].attack_length-1
        amplitude=esli.slices[self.sliceNum].amplitude
        
        self.entryStart.config(to=self.sample_length-1)
        self.entryStop.config(to=self.sample_length-1)
        self.entryAttack.config(to=self.sample_length-1)
        self.entryAmplitude.config(to=65536)
        
        self.start.set(start)
        self.stop.set(stop)
        self.attack.set(attack)
        self.amplitude.set(amplitude)
        
        self.lineSet.first = CVar(self.start,0,self.sample_length-1)
        self.lineSet.last = CVar(self.stop,-1,self.sample_length-1)
        self.lineSet.attack_last = CVar(self.attack,-1,self.sample_length-1)
        self.lineSet.amplitude = CVar(self.amplitude,0,65536)

        self.startTrace = self.start.trace('w', self._start_set)
        self.stopTrace = self.stop.trace('w', self._stop_set)
        self.attackTrace = self.attack.trace('w', self._attack_set)
        self.amplitudeTrace = self.amplitude.trace('w', self._amplitude_set)

        self._selected=False

    def _focus_in(self, event):
        if not self._selected:
            self.editor.wavDisplay.set_activeLineSet(self.lineSet)
            self.selected = True

    def _focus_out(self, event):
        if self._selected:
            self.editor.wavDisplay.set_activeLineSet()
            self.selected = False

    def _start_set(self, *args):
        start = self.start.get()
        if start > self.sample_length-1:
            self.start.set(self.sample_length-1)
            start = self.sample_length-1
        elif start < 0:
            self.start.set(0)
            start = 0
        if start > self.stop.get()+1:
            self.stop.set(start-1)
        if start > self.attack.get()+1:
            self.attack.set(start-1)

        self.esli.slices[self.sliceNum].start = start - self.esli.OSC_StartPoint_address//self.blockAlign
        # update the offsets
        self.esli.slices[self.sliceNum].length = self.stop.get()-start+1
        self.esli.slices[self.sliceNum].attack_length = self.attack.get()-start+1
        self.editor.wavDisplay.refresh(True)

    def _stop_set(self, *args):
        stop = self.stop.get()
        if stop > self.sample_length-1:
            self.stop.set(self.sample_length-1)
            stop = self.sample_length-1
        elif stop < -1:
            self.stop.set(-1)
            stop= -1
        if stop < self.start.get()-1:
            self.start.set(stop+1)
        if stop < self.attack.get():
            self.attack.set(stop)
        self.esli.slices[self.sliceNum].length = stop-self.start.get()+1
        self.editor.wavDisplay.refresh(True)

    def _attack_set(self, *args):
        attack = self.attack.get()
        if attack > self.sample_length-1:
            self.attack.set(self.sample_length-1)
            attack = self.sample_length-1
        elif attack < -1:
            self.attack.set(-1)
            attack = -1
        if attack < self.start.get()-1:
            self.start.set(attack+1)
        if attack > self.stop.get():
            self.stop.set(attack)

        self.esli.slices[self.sliceNum].attack_length = attack-self.start.get()+1
        self.editor.wavDisplay.refresh(True)

    def _amplitude_set(self, *args):
        amp = self.amplitude.get()
        if amp > 65536:
            self.amplitude.set(65536)
            amp = 65536
        elif amp < 0:
            self.amplitude.set(0)
            amp = 0

        self.esli.slices[self.sliceNum].amplitude = amp
        self.editor.wavDisplay.refresh(True)


    def _play(self, *args):
        start=self.start.get()*self.fmt.blockAlign
        stop=self.stop.get()*self.fmt.blockAlign
        if stop > 0:
            audio.player.play_start(audio.Sound(self.data[start:stop],self.fmt))

class FrameSlices(tk.Frame):
    def __init__(self, master, editor, *arg, **kwarg):
        super().__init__(master, *arg, **kwarg)
        
        tk.Label(self, text="First").grid(row=0, column=1)        
        tk.Label(self, text="Last").grid(row=0, column=2)        
        tk.Label(self, text="?Attack?").grid(row=0, column=3)        
        tk.Label(self, text="?Amplitude?").grid(row=0, column=4)

        self.slices = [Slice(self,editor,i) for i in range(64)]

    def set_sample(self, fmt, data, esli):
        for s in self.slices:
            s.set_sample(fmt,data,esli)

class NormalSampleOptions(tk.LabelFrame):
    def __init__(self, parent, editor, *arg, **kwarg):
        super().__init__(parent, *arg, **kwarg)
        
        self.editor = editor

        self.sound = None
        self.fmt = None
        self.data = None
        self.esli = None
        
        self.sample_length = 0

        tk.Label(self, text="Start").grid(row=1, column=1)
        tk.Label(self, text="End").grid(row=1, column=2)
        tk.Label(self, text="Loop start").grid(row=1, column=3)
        tk.Label(self, text="Play volume").grid(row=1, column=4)

        self.start = tk.IntVar()
        self.stop = tk.IntVar()
        self.loopStart = tk.IntVar()
        self.playVolume = tk.IntVar()
        
        self.start_trace = None
        self.stop_trace = None
        self.loopStart_trace = None
        self.playVolume_trace = None
        self.rootSet = None        
        
        tk.Label(self, text="Sample").grid(row=2, column=0)
        self.startEntry = SampleNumSpinbox(self, width=10, from_=0, to=0, textvariable=self.start, state='readonly')
        self.startEntry.grid(row=2, column=1)
        self.stopEntry = SampleNumSpinbox(self, width=10, from_=0, to=0, textvariable=self.stop, state='readonly')
        self.stopEntry.grid(row=2, column=2)
        self.loopStartEntry = SampleNumSpinbox(self, width=10, from_=0, to=0, textvariable=self.loopStart, state='readonly')
        self.loopStartEntry.grid(row=2, column=3)
        self.playVolumeEntry = SampleNumSpinbox(self, width=10, from_=0, to=65535, textvariable=self.playVolume, state='readonly')
        self.playVolumeEntry.grid(row=2, column=4)        
        self.buttonPlay = tk.Button(self, image=GUI.res.playIcon, command=self.play_start)
        self.buttonPlay.grid(row=2,column=5)
        self.buttonStop = tk.Button(self, image=GUI.res.stopIcon, command=self.play_stop)
        self.buttonStop.grid(row=2,column=6)
        
        self._selected=False
        self.startEntry.bind("<FocusIn>",self._focus_in,add="+")
        self.startEntry.bind("<FocusOut>",self._focus_out,add="+")
        self.stopEntry.bind("<FocusIn>",self._focus_in,add="+")
        self.stopEntry.bind("<FocusOut>",self._focus_out,add="+")
        self.loopStartEntry.bind("<FocusIn>",self._focus_in,add="+")
        self.loopStartEntry.bind("<FocusOut>",self._focus_out,add="+")
        self.playVolumeEntry.bind("<FocusIn>",self._focus_in,add="+")
        self.playVolumeEntry.bind("<FocusOut>",self._focus_out,add="+")

        self.lineSet = WaveDisplay.LineSet(self.start,self.stop,loop_first=self.loopStart)
        self.editor.wavDisplay.add_lineSet(self.lineSet)

    def play_start(self):
        # TODO: icon pause
        # TODO: see how to reduce delay (i.e. buffer size)
        #if self.sound is not None:
        #    self.sound.pause()
    
        # TODO: verrify meaning of each offset in esli (+ or - 1 or not )
        audio.player.play_start(audio.LoopWaveSource(self.data,self.fmt,self.esli))

    def play_stop(self):
        audio.player.play_stop()

    def set_sample(self, smpl_list, smpl_num):
        self.smpl_list = smpl_list
        self.smpl = smpl = smpl_list.e2s_samples[smpl_num]
        self.smpl_num = smpl_num

        fmt = smpl.get_fmt()
        data = smpl.get_data()
        esli = smpl.get_esli()

        self.fmt = fmt
        self.data = data.rawdata
        self.esli = esli
        self.blockAlign = fmt.blockAlign
        self.sample_length = len(data) // self.blockAlign

        self.oneshot = esli.OSC_OneShot

        if self.start_trace:
            self.start.trace_vdelete('w', self.start_trace)
        if self.stop_trace:
            self.stop.trace_vdelete('w', self.stop_trace)
        if self.loopStart_trace:
            self.loopStart.trace_vdelete('w', self.loopStart_trace)
        if self.playVolume_trace:
            self.playVolume.trace_vdelete('w', self.playVolume_trace)

        start=esli.OSC_StartPoint_address//self.blockAlign
        stop=start+esli.OSC_EndPoint_offset//self.blockAlign
        loopStart=start+esli.OSC_LoopStartPoint_offset//self.blockAlign
        playVolume=esli.playVolume
        
        self.startEntry.config(to=self.sample_length-1)
        self.stopEntry.config(to=self.sample_length-1)
        self.loopStartEntry.config(to=self.sample_length-1)
        
        self.start.set(start)
        self.stop.set(stop)
        self.loopStart.set(loopStart)
        self.playVolume.set(playVolume)
        
        self.start_trace = self.start.trace('w', self._start_set)
        self.stop_trace = self.stop.trace('w', self._stop_set)
        self.loopStart_trace = self.loopStart.trace('w', self._loopStart_set)
        self.playVolume_trace = self.playVolume.trace('w', self._playVolume_set)
        
        self.lineSet.first = CVar(self.start,0,self.sample_length-1)
        self.lineSet.last = CVar(self.stop,0,self.sample_length-1)
        self.lineSet.loop_first = CVar(self.loopStart,0,self.sample_length-1)
        self.lineSet.amplitude = CVar(self.playVolume,0,65535)

        self._selected=False

    def _focus_in(self, event):
        if not self._selected:
            self.editor.wavDisplay.set_activeLineSet(self.lineSet)
            self.selected = True

    def _focus_out(self, event):
        if self._selected:
            self.editor.wavDisplay.set_activeLineSet()
            self.selected = False

    def _start_set(self, *args):
        if self.rootSet is None:
            self.rootSet = self._start_set

            if self.loopStart.get() < self.start.get():
                self.loopStart.set(self.start.get())
            if self.stop.get() < self.start.get():
                self.stop.set(self.start.get())
            
            self.editor.wavDisplay.display_sample(self.start.get())
            self.rootSet = None

        start = self.start.get()
        prev_OSC_StartPoint_address = self.esli.OSC_StartPoint_address
        self.esli.OSC_StartPoint_address = start*self.blockAlign
        # update the offsets
        self.esli.OSC_LoopStartPoint_offset = (self.loopStart.get()-start)*self.blockAlign
        self.esli.OSC_EndPoint_offset = (self.stop.get()-start)*self.blockAlign
        # update slices
        for sliceNum in range(64):
            slice = self.esli.slices[sliceNum]
            if slice.length:
                slice.start += (prev_OSC_StartPoint_address - self.esli.OSC_StartPoint_address)//self.blockAlign
            else:
                # update interface to make slice starts at new startpoint (i.e. keep offset = 0)
                self.editor.slicedSampleOptions.frameSlices.slices[sliceNum].start.set(start)
                self.editor.slicedSampleOptions.frameSlices.slices[sliceNum].stop.set(start-1)

        self.editor.wavDisplay.set_activeLineSet(self.lineSet)
        self.editor.wavDisplay.refresh(True)

    def _stop_set(self, *args):
        if self.rootSet is None:
            self.rootSet = self._stop_set
            
            if self.start.get() > self.stop.get():
                self.start.set(self.stop.get())
            if self.loopStart.get() > self.stop.get():
                self.loopStart.set(self.stop.get())

            self.editor.wavDisplay.display_sample(self.stop.get())
            self.rootSet = None

        start = self.start.get()
        stop = self.stop.get()
        loopStart = self.loopStart.get()
        self.esli.OSC_EndPoint_offset = (stop-start)*self.blockAlign
        if self.rootSet is None and self.oneshot:
            # can't be oneShot and have loopStart != stop
            if loopStart != stop:
                self.esli.OSC_OneShot = False
            else:
                self.esli.OSC_OneShot = True
            self.smpl_list.update_sample(self.smpl_num)
        self.editor.wavDisplay.set_activeLineSet(self.lineSet)
        self.editor.wavDisplay.refresh(True)

    def _loopStart_set(self, *args):
        if self.rootSet is None:
            self.rootSet = self._loopStart_set
            
            if self.start.get() > self.loopStart.get():
                self.start.set(self.loopStart.get())
            if self.stop.get() < self.loopStart.get():
                self.stop.set(self.loopStart.get())

            self.editor.wavDisplay.display_sample(self.loopStart.get())
            self.rootSet = None

        start = self.start.get()
        stop = self.stop.get()
        loopStart = self.loopStart.get()
        self.esli.OSC_LoopStartPoint_offset = (loopStart-start)*self.blockAlign
        if self.rootSet is None and self.oneshot:
            # can't be oneShot and have loopStart != stop
            if loopStart != stop:
                self.esli.OSC_OneShot = False
            else:
                self.esli.OSC_OneShot = True
            self.smpl_list.update_sample(self.smpl_num)
        self.editor.wavDisplay.set_activeLineSet(self.lineSet)
        self.editor.wavDisplay.refresh(True)
    
    def _playVolume_set(self, *args):
        playVolume = self.playVolume.get()

        if playVolume > 65535:
            self.playVolume.set(65535)
            playVolume = 65535
        elif playVolume < 0:
            self.playVolume.set(0)
            playVolume = 0

        self.esli.playVolume = playVolume
        self.editor.wavDisplay.refresh(True)
class SlicedSampleOptions(tk.LabelFrame):
    def __init__(self, parent, editor, *arg, **kwarg):
        super().__init__(parent, *arg, **kwarg)

        self.frameSlices = FrameSlices(self, editor)
        self.frameSlices.pack(fill=tk.BOTH, expand=tk.YES)

    def set_sample(self, fmt, data, esli):
        self.frameSlices.set_sample(fmt,data,esli)

class SliceEditor(tk.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.esli=None

        # Some config width height settings
        canvas_width = 640
        canvas_height = 240

        self.wavDisplay = WaveDisplay(self, width=canvas_width, height=canvas_height)
        self.wavDisplay.pack(fill=tk.BOTH, expand=tk.YES, padx=2)
        self.h_scroll = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.scroll_wav)
        self.h_scroll.pack(fill=tk.X, expand=tk.NO, padx=2)
        self.wavDisplay.set_scrollBar(self.h_scroll)

        framezoom = tk.Frame(self)
        framezoom.pack(fill=tk.X, expand=tk.NO)
        tk.Label(framezoom,text="Zoom:").pack(side=tk.LEFT)
        self.zoomVar=tk.StringVar()
        self.zoomVar.trace("w",self._zoom_edit)
        self.zoomEdit = ROSpinbox(framezoom, values=('all',), textvariable=self.zoomVar)
        self.zoomEdit.pack(side=tk.LEFT)
        
        self.frame = VerticalScrolledFrame(self)
        self.frame.pack(fill=tk.BOTH, expand=tk.YES)

        self.normalSampleOptions = NormalSampleOptions(self.frame.interior, self, text="Normal sample options")
        self.normalSampleOptions.pack(side=tk.TOP, fill=tk.BOTH, expand=tk.NO)

        self.slicedSampleOptions = SlicedSampleOptions(self.frame.interior, self, text="Sliced sample options")
        self.slicedSampleOptions.pack(side=tk.TOP, fill=tk.BOTH, expand=tk.NO)

        frame = tk.Frame(self.frame.interior)
        frame.pack()
        
        self.slicedRadioV = tk.BooleanVar()
        self.radioUseNormal = tk.Radiobutton(frame, text="Normal sample", variable=self.slicedRadioV, value=False, state=tk.DISABLED)
        self.radioUseNormal.grid(row=0,column=0,sticky=tk.W)        

        self.radioUseSliced = tk.Radiobutton(frame, text="Sliced sample", variable=self.slicedRadioV, value=True, state=tk.DISABLED)
        self.radioUseSliced.grid(row=1,column=0,sticky=tk.W)

        tk.Label(frame,text="Steps").grid(row=0,column=1,sticky=tk.E)
        tk.Label(frame,text="/").grid(row=0,column=2)
        tk.Label(frame,text="Beat").grid(row=0,column=3,sticky=tk.W)
        tk.Label(frame,text="Active Steps").grid(row=0,column=4)
        
        self.numSteps = tk.IntVar()
        self.numStepsTrace = None
        self.numActiveSteps = tk.IntVar()
        self.numActiveStepsTrace = None
        self.numStepsEdit = ROSpinbox(frame, from_=0, to=64, width=2, textvariable=self.numSteps)
        self.numStepsEdit.grid(row=1,column=1,sticky=tk.E)
        tk.Label(frame,text="/").grid(row=1,column=2)
        self.beat = tk.StringVar()
        self.beatTrace = None
        self.beatEdit = ROSpinbox(frame, values=tuple(sorted(e2s.esli_beat, key=e2s.esli_beat.get)), width=6, textvariable=self.beat)
        self.beatEdit.grid(row=1,column=3,sticky=tk.W)
        self.numActiveStepsEntry = tk.Entry(frame, width=2, textvariable=self.numActiveSteps, state=tk.DISABLED)
        self.numActiveStepsEntry.grid(row=1,column=4)

        frame = tk.Frame(self.frame.interior)
        frame.pack()

        self.activeSteps= []
        self.activeStepsTrace = []
        for j in range(64):
            self.activeSteps.append(tk.StringVar())
            self.activeStepsTrace.append(None)
        
        self.activeStepsEntry = []
        for j in range(4):
            tk.Label(frame, text="Step : ").grid(row=j*2+0, column=0)
            tk.Label(frame, text="Slice : ").grid(row=j*2+1, column=0)
            for i in range(16):
                tk.Label(frame, text=j*16+i+1).grid(row=j*2+0,column=i+1)
                self.activeStepsEntry.append(ROSpinbox(frame, values=("Off",)+tuple(range(64)), width=3, textvariable=self.activeSteps[j*16+i]))
                # bug? 'textvariable' must be configured later than 'values' to be used
                #self.activeStepsEntry[j*16+i].config(textvariable=self.activeSteps[j*16+i])
                self.activeStepsEntry[j*16+i].grid(row=j*2+1,column=i+1)
        
        tk.Button(frame, text="Off them all", command=self.allActiveStepsOff).grid(row=8, column=0, columnspan=17, padx=5, pady=5)

    def allActiveStepsOff(self):
        for j in range(64):
            self.activeSteps[j].set("Off")

    def _zoom_edit(self, *args):
        zoomStr = self.zoomVar.get()
        
        if zoomStr == 'all':
            self.wavDisplay.set_disp(0,self.wavDisplay.wav_length())
        else:
            zoom = float(zoomStr)
            self.wavDisplay.set_zoom_x(zoom)
        
    
    def scroll_wav(self, command, *args):
        if command == tk.MOVETO:
            offset = float(args[0])
            scroll_tot = self.wavDisplay.wav_length()
            self.wavDisplay.scroll_to(scroll_tot * offset)
        elif command == tk.SCROLL:
            step = float(args[0])
            what = args[1]
            
            if what == "units":
                self.wavDisplay.scroll_pix_stop(step*16)
            elif what == "pages":
                self.wavDisplay.scroll_pix_stop(step*self.wavDisplay.width/2)
            else:
                raise Exception("Unknown scroll unit: " + what)

    def set_sample(self, smpl_list, smpl_num):
        self.smpl = smpl = smpl_list.e2s_samples[smpl_num]

        fmt = smpl.get_fmt()
        data = smpl.get_data()
        esli = smpl.get_esli()

        self.esli = esli
        self.zoomVar.set('all')
        #compute zoom 'all' factor:
        zoom_all = self.wavDisplay.width/(len(data)//fmt.blockAlign)
        zooms = [16., 8., 4., 2., 1.]
        curr_zoom=0.5
        while curr_zoom > zoom_all:
            zooms.append(curr_zoom)
            curr_zoom /= 2
        zooms.append('all')
        zooms.reverse()
        self.zoomEdit.config(values=tuple(zooms))
        #self.zoomEdit.config(values=('all', 0.0625, 0.125, 0.25, 0.5, 1. ,2. ,4., 8., 16.))
        self.wavDisplay.set_wav(fmt, data)
        self.normalSampleOptions.set_sample(smpl_list, smpl_num)
        self.slicedSampleOptions.set_sample(fmt, data, esli)
        
        if self.numActiveStepsTrace:
            self.numActiveSteps.trace_vdelete('w', self.numActiveStepsTrace)

        for j in range(64):
            if self.activeStepsTrace[j]:
                self.activeSteps[j].trace_vdelete('w', self.activeStepsTrace[j])
            self.activeSteps[j].set(str(esli.sliceSteps[j]) if esli.sliceSteps[j] >= 0 else "Off")
            self.activeStepsTrace[j] =  self.activeSteps[j].trace('w', lambda *args, j=j: self._activeStepEdit(j))

        if self.numStepsTrace:
            self.numSteps.trace_vdelete('w', self.numStepsTrace)
        self.numSteps.set(esli.slicingNumSteps)
        self.numStepsTrace = self.numSteps.trace('w', self._numStepsEdit)
                
        if self.beatTrace:
            self.beat.trace_vdelete('w', self.beatTrace)
        self.beat.set(e2s.esli_beat_to_str.get(esli.slicingBeat))
        self.beatTrace = self.beat.trace('w', self._beatEdit)

        self.numActiveSteps.set(esli.slicesNumActiveSteps)
        self.numActiveStepsTrace = self.numActiveSteps.trace('w', self._numActiveStepsChanged)
        
        self.slicedRadioV.set(self.numActiveSteps.get()>0)

        #reset view point of vertical scroll
        self.frame.canvas.xview_moveto(0)
        self.frame.canvas.yview_moveto(0)

    def _activeStepEdit(self, index):
        value = self.activeSteps[index].get()
        self.esli.sliceSteps[index] = int(value) if value != "Off" else -1
        self._updateSlicesNumActiveSteps()
        
    def _numStepsEdit(self, *args):
        numSteps = self.numSteps.get()
        self.esli.slicingNumSteps = numSteps
        self._updateSlicesNumActiveSteps()
        #self.slicedRadioV.set(numSteps>0)
        
    def _beatEdit(self, *args):
        self.esli.slicingBeat = e2s.esli_beat.get(self.beat.get())
        self._limitNumSteps()
        self._updateSlicesNumActiveSteps()
    
    def _limitNumSteps(self):
        if self.beat.get() in ('8 Tri','16 Tri'):
            self.numStepsEdit.config(to=48)
            if self.numSteps.get() > 48:
                self.numSteps.set(48)
        else:
            self.numStepsEdit.config(to=64)
        
        
    def _updateSlicesNumActiveSteps(self):
        numActiveSteps=0
        for i in range(self.numSteps.get()):
            numActiveSteps += 1 if self.activeSteps[i].get() != "Off" else 0
        self.numActiveSteps.set(numActiveSteps)
    
    def _numActiveStepsChanged(self, *args):
        self.esli.slicesNumActiveSteps = self.numActiveSteps.get()
        self.slicedRadioV.set(self.numActiveSteps.get()>0)

class SliceEditorDialog(tk.Toplevel):
    system = platform.system()
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.withdraw()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.on_delete)
        
        self.sliceEditor = SliceEditor(self)
        self.sliceEditor.pack(fill=tk.BOTH, expand=tk.YES)

        if self.system == 'Windows':
            def _on_mousewheel(event):
                self.sliceEditor.frame.canvas.yview_scroll(-1*(event.delta//120), "units")
            self.bind('<MouseWheel>', _on_mousewheel)
        elif self.system == 'Darwin':
            def _on_mousewheel(event):
                self.sliceEditor.frame.canvas.yview_scroll(-1*(event.delta), "units")
            self.bind('<MouseWheel>', _on_mousewheel)
        else:
            def _on_up(event):
                self.sliceEditor.frame.canvas.yview_scroll(-1, "units")
            def _on_down(event):
                self.sliceEditor.frame.canvas.yview_scroll(1, "units")
            self.bind('<Button-4>', _on_up)
            self.bind('<Button-5>', _on_down)

    def run(self):
        self.deiconify()
        
        self.grab_set()        
        
        self.focus_set()
        
    def on_delete(self):
        audio.player.play_stop()
        self.withdraw()
        
        parent=self.master
        parent.grab_set()
        parent.focus_set()

class Sample(object):
    OSC_caths = tuple(
        e2s.esli_OSC_cat_to_str[k]
        for k in sorted(e2s.esli_OSC_cat_to_str))

    def __init__(self, master, line_num, sample_num):
        self.master = master
        self.frame = master.frame

        self.name = tk.StringVar()
        self.oscNum = tk.IntVar()
        self.oneShot = tk.BooleanVar()
        self.plus12dB = tk.BooleanVar()
        self.tuneVal = tk.IntVar()
        self.samplingFreq= tk.IntVar()
        self.stereo=tk.BooleanVar()
        self.smpSize=tk.IntVar()

        self.name_trace = None
        self.oscNum_trace = None
        self.oneShot_trace = None
        self.plus12dB_trace = None
        self.tuneVal_trace = None

        self.radioButton = tk.Radiobutton(self.frame, variable=self.master.selectV)
        self.replaceButton = tk.Button(self.frame, image=GUI.res.replaceIcon, command=self._on_replace)
        self.exportButton = tk.Button(self.frame, image=GUI.res.exportIcon, command=self._on_export)
        self.durationEntry = tk.Label(self.frame, width=8, state=tk.DISABLED, relief=tk.SUNKEN, anchor=tk.E)
        self.entryOscCat = ROCombobox(self.frame, values=Sample.OSC_caths, width=8, command=self._oscCat_set)
        self.entryOscNum = SampleNumSpinbox(self.frame,width=3, textvariable=self.oscNum,command=self._oscNum_command)
        # RIFF_korg_esli.playLogPeriod has a 0.5814686990855805 to 1536036.6940220615 frequency range
        self.samplingFreqEntry = SampleNumSpinbox(self.frame, width=8, textvariable=self.samplingFreq, justify=tk.RIGHT, from_=1, to=1536036, command=self._samplingFreq_command)
        self.entryName = tk.Entry(self.frame, width=16, textvariable=self.name)
        self.checkOneShot = tk.Checkbutton(self.frame, variable=self.oneShot)
        self.check12dB = tk.Checkbutton(self.frame, variable=self.plus12dB)
        self.entryTune = ROSpinbox(self.frame, from_=-63, to=63, width=3, format='%2.0f', textvariable=self.tuneVal)
        self.buttonPlay = tk.Button(self.frame, image=GUI.res.playIcon, command=self.play)
        self.checkStereo = tk.Checkbutton(self.frame, variable=self.stereo, command=self._stereo_command)
        self.sizeEntry = tk.Entry(self.frame, width=8, textvariable=self.smpSize, state=tk.DISABLED, justify=tk.RIGHT)
        self.buttonEdit = tk.Button(self.frame, image=GUI.res.editIcon, command=self._on_edit)
        self.buttonDelete = tk.Button(self.frame, image=GUI.res.trashIcon, command=self._on_delete)

        ToolTip(self.replaceButton, follow_mouse=1, text="import replacement sample")
        ToolTip(self.exportButton, follow_mouse=1, text="export sample")
        ToolTip(self.buttonPlay, follow_mouse=1, text="play full WAV content\n(start/loop/end are ignored)")
        ToolTip(self.buttonEdit, follow_mouse=1, text="edit loop/slices points")
        ToolTip(self.buttonDelete, follow_mouse=1, text="delete")

        self.restore(line_num, sample_num)

    def restore(self, line_num, sample_num):
        self.set_sample_num(sample_num)
        self.grid(line_num+1)

    def grid(self, row):
        self.radioButton.grid(row=row, column=0)
        self.replaceButton.grid(row=row, column=2)
        self.entryOscNum.grid(row=row, column=3)
        self.entryName.grid(row=row, column=4)
        self.entryOscCat.grid(row=row, column=5)
        self.checkOneShot.grid(row=row,column=6)
        self.check12dB.grid(row=row,column=7)
        self.entryTune.grid(row=row,column=8)
        self.buttonPlay.grid(row=row, column=9)
        self.samplingFreqEntry.grid(row=row, column=10)
        self.durationEntry.grid(row=row, column=11)
        self.checkStereo.grid(row=row, column=12)
        self.sizeEntry.grid(row=row, column=13)
        self.buttonEdit.grid(row=row, column=14, padx=10)
        self.exportButton.grid(row=row, column=15, padx=10)
        self.buttonDelete.grid(row=row, column=16, padx=10)

    def forget(self):
        self.radioButton.grid_forget()
        self.replaceButton.grid_forget()
        self.exportButton.grid_forget()
        self.entryOscNum.grid_forget()
        self.entryName.grid_forget()
        self.entryOscCat.grid_forget()
        self.checkOneShot.grid_forget()
        self.check12dB.grid_forget()
        self.entryTune.grid_forget()
        self.buttonPlay.grid_forget()
        self.samplingFreqEntry.grid_forget()
        self.durationEntry.grid_forget()
        self.checkStereo.grid_forget()
        self.sizeEntry.grid_forget()
        self.buttonEdit.grid_forget()
        self.buttonDelete.grid_forget()

    def destroy(self):
        self.radioButton.destroy()
        self.replaceButton.destroy()
        self.exportButton.destroy()
        self.entryOscNum.destroy()
        self.entryName.destroy()
        self.entryOscCat.destroy()
        self.checkOneShot.destroy()
        self.check12dB.destroy()
        self.entryTune.destroy()
        self.buttonPlay.destroy()
        self.samplingFreqEntry.destroy()
        self.durationEntry.destroy()
        self.checkStereo.destroy()
        self.sizeEntry.destroy()
        self.buttonEdit.destroy()
        self.buttonDelete.destroy()

    def set_sample_num(self, sample_num):
        self.sample_num = sample_num
        self.e2s_sample = self.master.e2s_samples[sample_num]
        self.reset_vars()

    def reset_vars(self):
        if self.name_trace:
            self.name.trace_vdelete('w', self.name_trace)
        if self.oscNum_trace:
            self.oscNum.trace_vdelete('w', self.oscNum_trace)
        self.entryOscNum.config(textvariable=None)
        if self.oneShot_trace:
            self.oneShot.trace_vdelete('w', self.oneShot_trace)
        if self.plus12dB_trace:
            self.plus12dB.trace_vdelete('w', self.plus12dB_trace)
        if self.tuneVal_trace:
            self.tuneVal.trace_vdelete('w', self.tuneVal_trace)

        esli = self.e2s_sample.get_esli()
        fmt = self.e2s_sample.get_fmt()
        data = self.e2s_sample.get_data()

        self.entryOscNum.config(from_=self.sample_num+19 if self.sample_num+19<422 else self.sample_num+19+79, to=999)

        self.radioButton.config(value=self.sample_num)
        self.name.set(esli.OSC_name.decode('ascii', 'ignore').split('\x00')[0])
        self.oscNum.set(esli.OSC_0index+1)
        self.entryOscNum._prev = self.oscNum.get()
        self.entryOscCat.set(Sample.OSC_caths[esli.OSC_category])
        self.oneShot.set(esli.OSC_OneShot)
        self.plus12dB.set(esli.playLevel12dB)
        self.tuneVal.set(esli.sampleTune)
        self.samplingFreq.set(esli.samplingFreq)
        if fmt.samplesPerSec != esli.samplingFreq:
            print("Warning: sampling frequency differs between esli and fmt")
        self.durationEntry.config(text="{:.4f}".format(len(data)/fmt.avgBytesPerSec if fmt.avgBytesPerSec else 0))
        self.stereo.set(fmt.channels > 1)
        self.smpSize.set(len(data))

        self.name_trace = self.name.trace('w', self._name_set)
        self.oscNum_trace = self.oscNum.trace('w', self._oscNum_set)
        self.oneShot_trace = self.oneShot.trace('w', self._oneShot_set)
        self.plus12dB_trace = self.plus12dB.trace('w', self._plus12dB_set)
        self.tuneVal_trace = self.tuneVal.trace('w', self._tuneVal_set)
        self.entryOscNum.config(textvariable=self.oscNum)
    
    def _name_set(self, *args):
        # electribe sampler uses a subset of the ascii encoding
        esli = self.e2s_sample.get_esli()
        esli.OSC_name = bytes(self.name.get(),'ascii', 'ignore')
        self.name.set(esli.OSC_name.decode('ascii').rstrip('\x00'))
    
    def _oscNum_set(self, *args):
        oscNum = self.oscNum.get()
        if 422 <= oscNum <= 500:
            if self.entryOscNum._prev < oscNum:
                self.oscNum.set(501)
            else:
                self.oscNum.set(421)
            oscNum = self.oscNum.get()
        self.e2s_sample.get_esli().OSC_0index = oscNum-1
        self.e2s_sample.get_esli().OSC_0index1 = oscNum-1
        self.entryOscNum._prev = oscNum
    
    def _oscNum_command(self):
        oscNum = self.oscNum.get()
        lN = self.sample_num
        e2s_samples = self.master.e2s_samples

        maxval = 1000-len(e2s_samples)+lN
        if maxval <= 500:
            maxval -= 79
        
        if oscNum > maxval:
            self.oscNum.set(maxval)
            oscNum = self.oscNum.get()
        
        if lN and e2s_samples[lN-1].get_esli().get_OSCNum() >= oscNum:
            # was decreased
            # check that we will not go under 19 is not necessary while 
            # is setself.entryOscNum.config(from_=sample_num+19, to=999)
            while lN and e2s_samples[lN-1].get_esli().get_OSCNum() >= e2s_samples[lN].get_esli().get_OSCNum():
                nextOSCNum = e2s_samples[lN].get_esli().get_OSCNum()
                e2s_samples[lN-1].get_esli().set_OSCNum(nextOSCNum-1 if nextOSCNum != 501 else 421)
                lN -= 1
                self.master.update_sample(lN)
        elif lN < len(e2s_samples)-1 and e2s_samples[lN+1].get_esli().get_OSCNum() <= oscNum:
            # was increased, look if possible
            #if len(samples)-1 - lN <= 999 - oscNum:
            while lN < len(e2s_samples)-1 and e2s_samples[lN+1].get_esli().get_OSCNum() <= e2s_samples[lN].get_esli().get_OSCNum():
                prevOSCNum = e2s_samples[lN].get_esli().get_OSCNum()
                e2s_samples[lN+1].get_esli().set_OSCNum(prevOSCNum+1 if prevOSCNum != 421 else 501)
                lN += 1
                self.master.update_sample(lN)
            #else:
            #    self.oscNum.set(oscNum-1)

    def _oscCat_set(self, *args):
        self.e2s_sample.get_esli().OSC_category = e2s.esli_str_to_OSC_cat[self.entryOscCat.get()]
    
    def _oneShot_set(self, *args):
        oneShot = self.oneShot.get()
        if oneShot and self.e2s_sample.get_esli().OSC_LoopStartPoint_offset != self.e2s_sample.get_esli().OSC_EndPoint_offset:
            if tk.messagebox.askyesno("Loop Start is set", "Loop start shall be reset to allow one shot.\nContinue?"):
                self.e2s_sample.get_esli().OSC_LoopStartPoint_offset = self.e2s_sample.get_esli().OSC_EndPoint_offset
                self.e2s_sample.get_esli().OSC_OneShot = oneShot
            else:
                self.oneShot.set(False)
                # update checkbutton
                self.checkOneShot.config(state=tk.NORMAL)
        else:
            self.e2s_sample.get_esli().OSC_OneShot = oneShot
        
    def _plus12dB_set(self, *args):
        self.e2s_sample.get_esli().playLevel12dB = self.plus12dB.get()
    
    def _tuneVal_set(self, *args):
        self.e2s_sample.get_esli().sampleTune = self.tuneVal.get()
    
    def _samplingFreq_command(self, *ars):
        sFreq = self.samplingFreq.get()
        esli = self.e2s_sample.get_esli()
        fmt = self.e2s_sample.get_fmt()
        data = self.e2s_sample.get_data()
        esli.samplingFreq = sFreq
        # by default play speed is same as indicated by Frequency
        esli.playLogPeriod = 65535 if sFreq == 0 else max(0, int(round(63132-math.log2(sFreq)*3072)))
        fmt.samplesPerSec = sFreq
        fmt.avgBytesPerSec = sFreq*fmt.blockAlign
        self.durationEntry.config(text="{:.4f}".format(len(data)/fmt.avgBytesPerSec if fmt.avgBytesPerSec else 0))

    def _stereo_command(self,*args):
        # don't switch immediately
        self.stereo.set(not self.stereo.get())
        if not self.stereo.get():
            # mono can't be set to stereo
            return
        dialog = StereoToMonoDialog(self.checkStereo, self.e2s_sample)
        self.master.wait_window(dialog)
        fmt = self.e2s_sample.get_fmt()
        self.stereo.set(fmt.channels > 1)
        data = self.e2s_sample.get_data()
        self.smpSize.set(len(data))
        self.master.update_WAVDataSize()

    def _on_replace(self):
        filename = tk.filedialog.askopenfilename(parent=self.master.parent, title="Select replacement WAV file",filetypes=(('Wav Files','*.wav'), ('All Files','*.*')))
        def fct():
            num_converted = dict()
            res = self.master.parent._import_sample_helper(filename)

            if res:
                sample, converted_from, converted_to_mono = res
                esli = sample.get_esli()
                esli.OSC_0index = esli.OSC_0index1 = self.e2s_sample.get_esli().OSC_0index
                self.master.e2s_samples[self.sample_num] = sample
                self.master.update_sample(self.sample_num)
                self.master.update_WAVDataSize()

                if converted_from or converted_to_mono:
                    conversion = (
                        ["from {} bits to 16 bits".format(converted_from)] if converted_from else []
                        + ["to mono"] if converted_to_mono else []
                        )
                    tk.messagebox.showinfo(
                        "Import WAV",
                        "'{}' file converted {}.\n".format(filename, " and ".join(conversion))
                        )
        if filename:
            wd = WaitDialog(self.master.parent)
            wd.run(fct)

    def _on_export(self):
        self.master.export(self.e2s_sample)

    def _on_edit(self):
        self.master.edit(self.sample_num)

    def _on_delete(self):
        self.master.remove(self.sample_num)

    def play(self):
        # TODO: have a single wav player for the whole application
        self.master.play(self.e2s_sample)
        
class SampleList(tk.Frame):
    def __init__(self, parent, *arg, **kwarg):
        super().__init__(*arg, **kwarg)
        self.vscrollbar = tk.ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.on_scroll)
        self.vscrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, confine=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.frame = tk.Frame(self.canvas)
        self.frame_id = self.canvas.create_window(0, 0, window=self.frame, anchor=tk.NW)

        self.parent = parent

        self.stopButton = tk.Button(self.frame, image=GUI.res.stop_smallIcon, command=self.play_stop)
        ToolTip(self.stopButton, follow_mouse=1, text="stop playback")

        tk.Label(self.frame, text="#Num").grid(row=0, column=3)
        tk.Label(self.frame, text="Name").grid(row=0, column=4)
        tk.Label(self.frame, text="Cat.").grid(row=0, column=5)
        tk.Label(self.frame, text="1-shot").grid(row=0, column=6)
        tk.Label(self.frame, text="+12dB").grid(row=0, column=7)
        tk.Label(self.frame, text="Tune").grid(row=0, column=8)
        self.stopButton.grid(row=0, column=9, padx=5)
        tk.Label(self.frame, text="Freq (Hz)").grid(row=0, column=10)
        tk.Label(self.frame, text="Time (s)").grid(row=0, column=11)
        tk.Label(self.frame, text="Stereo").grid(row=0,column=12)
        tk.Label(self.frame, text="Data Size").grid(row=0, column=13)

        tk.Frame(self.frame, width=2, bd=1, relief=tk.SUNKEN).grid(row=0, column=1, rowspan=999, sticky=tk.N+tk.S)
        self.fill = tk.Label(self.frame)
        self.fill.grid(row=998, column=2, columnspan=12, sticky=tk.NSEW)
        tk.Grid.rowconfigure(self.frame, 998, weight=1)
        self.fill.config(height=self.canvas.winfo_reqheight())

        self.sliceEditDialog = None

        self.selectV = tk.IntVar()

        self.WAVDataSize = tk.IntVar()

        self.samples = []
        self.samples_garbage = []
        self.e2s_samples = []

        self.update_scrollbar()

        # track changes to the canvas and frame width and sync them,
        def _configure_frame(event):
            # update the canvas's width to fit the inner frame
            if self.canvas.winfo_reqwidth() != self.frame.winfo_reqwidth():
                self.canvas.config(width=self.frame.winfo_reqwidth())
        self.frame.bind('<Configure>', _configure_frame)
        self.canvas.bind('<Configure>', self._on_configure)

    def _on_configure(self, event):
        if self.canvas.winfo_height() != self.fill.winfo_height():
            self.fill.config(height=self.canvas.winfo_height())
        if not self.samples:
            return
        # update the inner frame's height to fill the canvas
        new_h = event.height
        _, _, _, h = self.frame.grid_bbox(0,0,0,0)
        h_max = event.height - h
        _, _, _, h_line = self.frame.grid_bbox(0,1,0,1)
        while h_line*(len(self.samples)+1) <= h_max and len(self.samples)+1 <= len(self.e2s_samples):
            sample_num=self.samples[-1].sample_num+1
            if sample_num >= len(self.e2s_samples):
                self.scroll(-1)
                sample_num = len(self.e2s_samples)-1
            self.push_sample(sample_num)
        while len(self.samples)*h_line > h_max:
            self.pop_sample()

        self.update_scrollbar()

    # this is to handle an issue with tkinter:
    # if you destroy a Sample the canvas is resized to its req_height
    def pop_sample(self):
        self.samples_garbage.append(self.samples.pop())
        self.samples_garbage[-1].forget()
    def push_sample(self, sample_num):
        if not self.samples_garbage:
            smpl = Sample(self,len(self.samples),sample_num)
        else:
            smpl = self.samples_garbage.pop()
            smpl.restore(len(self.samples),sample_num)
        self.samples.append(smpl)

    def find_max_sample_0index(self):
        # e2s_samples are currently ordered by OSC_0index
        if self.e2s_samples:
            return self.e2s_samples[-1].get_esli().OSC_0index
        else:
            return 17

    def get_next_free_sample_index(self, _from=None):
        if _from is None:
            max = self.find_max_sample_0index()
            if 420 == max:
                max = 499
            if max<998:
                return max+1
            else:
                _from = 18
        else:
            # max is 998, find first free
            # e2s_samples are currently ordered by OSC_0index
            next=_from
            for e2s_sample in self.e2s_samples:
                curr = e2s_sample.get_esli().OSC_0index
                if curr > next:
                    break
                if curr >= _from:
                    next = curr+1 if curr != 420 else 500
            return next if next < 999 else (
                None if _from == 18 else self.get_next_free_sample_index(18))

    def get_next_free_index(self, direction=1, first=None, roll=False):
        if not direction:
            return self.get_next_free_sample_index()
        if first is None:
            if direction > 0:
                curr = 0
            if direction < 0:
                curr = 998
        else:
            curr = first
        # find sample number in the sample list
        curr_smp_num = 0 if direction > 0 else len(self.e2s_samples)-1
        while (direction > 0
               and curr_smp_num < len(self.e2s_samples)
               and self.e2s_samples[curr_smp_num].get_esli().OSC_0index < curr
               or direction < 0
               and curr_smp_num >= 0
               and self.e2s_samples[curr_smp_num].get_esli().OSC_0index > curr
               ):
            curr_smp_num += 1 if direction > 0 else -1
        # find next free sample number
        while (direction > 0
               and curr_smp_num < len(self.e2s_samples)
               and self.e2s_samples[curr_smp_num].get_esli().OSC_0index == curr
               or direction < 0
               and curr_smp_num >= 0
               and self.e2s_samples[curr_smp_num].get_esli().OSC_0index == curr
               ):
            curr_smp_num += 1 if direction > 0 else -1
            curr += 1 if direction > 0 else -1
            if 420 < curr < 500:
                curr = 500 if direction > 0 else 420
        if curr < 18 or curr > 998:
            if not roll:
                return None
            else:
                return self.get_next_free_index(direction, 18 if direction > 0 else 998)
        else:
            return (curr_smp_num, curr)

    def get_selected(self):
        if 0 <= self.selectV.get() < len(self.e2s_samples):
            self.show_selected()
            return self.selectV.get()
        else:
            return None

    def update_WAVDataSize(self):
        self.WAVDataSize.set(sum(len(s.get_data()) for s in self.e2s_samples))

    def update_scrollbar(self):
        if self.e2s_samples:
            self.vscrollbar.set(self.samples[0].sample_num/len(self.e2s_samples), (self.samples[-1].sample_num+1)/len(self.e2s_samples))
        else:
            self.vscrollbar.set(0, 1)

    def on_scroll(self, command, *args):
        if command == tk.MOVETO:
            offset = float(args[0])
            scroll_tot = len(self.e2s_samples)
            self.scroll_to(scroll_tot * offset)
        elif command == tk.SCROLL:
            step = float(args[0])
            what = args[1]

            if what == "units":
                self.scroll(step)
            elif what == "pages":
                self.scroll(step*len(self.samples))
            else:
                raise Exception("Unknown scroll unit: " + what)

    def scroll(self, offset):
        if len(self.samples):
            self.scroll_to(self.samples[0].sample_num+offset)

    def scroll_to(self, offset):
        sample_num = max(0,min(int(offset),len(self.e2s_samples)-len(self.samples)))
        for sample in self.samples:
            sample.set_sample_num(sample_num)
            sample_num += 1
        self.update_scrollbar()

    def add_new(self, e2s_sample):
        self.e2s_samples.append(e2s_sample)
        self.WAVDataSize.set(self.WAVDataSize.get()+len(self.e2s_samples[-1].get_data()))
        smp_num=len(self.e2s_samples)-1
        osc_num=e2s_sample.get_esli().get_OSCNum()
        #sort
        while smp_num > 0:
            pr_osc_num = self.e2s_samples[smp_num-1].get_esli().get_OSCNum()
            if osc_num > pr_osc_num:
                break
            # swap samples
            self.e2s_samples[smp_num], self.e2s_samples[smp_num-1] = self.e2s_samples[smp_num-1], self.e2s_samples[smp_num]
            smp_num -= 1
        insert_num=smp_num
        # add new sample line if necessary
        n_lines = len(self.samples)
        _, _, _, h = self.frame.grid_bbox(0,0,0,0)
        h_max = self.canvas.winfo_height()-h
        _, _, _, h_line = self.frame.grid_bbox(0,1,0,1)
        if not n_lines or h_line*(n_lines+1) <= h_max and len(self.samples) < len(self.e2s_samples):
            self.push_sample(len(self.e2s_samples)-1)
        # update selected sample
        if len(self.e2s_samples) > 1 and self.selectV.get() >= smp_num:
            self.selectV.set(smp_num+1)
        # update sample objects
        while smp_num < len(self.e2s_samples):
            self.update_sample(smp_num)
            smp_num += 1
        self.update_scrollbar()

    def remove(self, sample_num):
        if 0 <= sample_num < len(self.e2s_samples):
            e2s_sample = self.e2s_samples.pop(sample_num)
            self.WAVDataSize.set(self.WAVDataSize.get()-len(e2s_sample.get_data()))
            first = self.samples[0].sample_num
            last = self.samples[-1].sample_num
            if last >= sample_num >= first:
                # move samples
                if first > 0:
                    # down
                    for s in self.samples:
                        s.set_sample_num(s.sample_num-1)
                else:
                    #up
                    for i in range(sample_num-first,last-first):
                        self.samples[i].set_sample_num(first+i)
                    if self.samples[-1].sample_num < len(self.e2s_samples):
                        self.samples[-1].set_sample_num(last)
                    else:
                        smpl = self.samples.pop()
                        smpl.destroy()
                #TODO: actualize scroll-bar
            if self.selectV.get() >= len(self.e2s_samples):
                self.selectV.set(self.selectV.get()-1)
            self.update_scrollbar()

    def clear(self):
        for sample in reversed(self.samples):
            sample.destroy()
        self.samples.clear()
        self.e2s_samples.clear()
        self.WAVDataSize.set(0)
        self.selectV.set(0)
        self.update_scrollbar()

    def update_sample(self, sample_num):
        if self.samples and self.samples[0].sample_num <= sample_num <= self.samples[-1].sample_num:
            self.samples[sample_num-self.samples[0].sample_num].set_sample_num(sample_num)


    def exchange(self, a, b, keep_index=False):
        if not keep_index:
            # swap osc indexes
            a_esli = self.e2s_samples[a].get_esli()
            b_esli = self.e2s_samples[b].get_esli()
            a_index = a_esli.OSC_0index
            a_esli.OSC_0index=a_esli.OSC_0index1=b_esli.OSC_0index
            b_esli.OSC_0index=b_esli.OSC_0index1=a_index
        # swap samples
        self.e2s_samples[a], self.e2s_samples[b] = self.e2s_samples[b], self.e2s_samples[a]
        # update sample objects
        self.update_sample(a)
        self.update_sample(b)

    def move_up(self, line_num, keep_index=False):
        if 0 < line_num < len(self.e2s_samples):
            self.exchange(line_num, line_num-1, keep_index)
            return True
        return False

    def move_down(self, line_num, keep_index=False):
        if 0 <= line_num < len(self.e2s_samples)-1:
            self.exchange(line_num, line_num+1, keep_index)
            return True
        return False

    def set_selected(self, num):
        self.selectV.set(num)
        self.show_selected()


    def show_selected(self):
        selected = self.selectV.get()
        if 0 <= selected and self.samples[0].sample_num > selected:
            self.scroll_to(selected)
        elif len(self.e2s_samples) > selected and self.samples[-1].sample_num < selected:
            self.scroll_to(1+selected-len(self.samples))

    def move_up_selected(self):
        if self.move_up(self.selectV.get()):
            self.selectV.set(self.selectV.get()-1)
            self.show_selected()

    def move_down_selected(self):
        if self.move_down(self.selectV.get()):
            self.selectV.set(self.selectV.get()+1)
            self.show_selected()

    def move_up_selected_to_next_free(self):
        selected = self.selectV.get()
        if 0 <= selected < len(self.e2s_samples):
            res = self.get_next_free_index(-1, self.e2s_samples[selected].get_esli().OSC_0index)
            if res:
                list_idx, osc_idx = res
                esli = self.e2s_samples[selected].get_esli()
                esli.OSC_0index = esli.OSC_0index1 = osc_idx
                self.update_sample(selected)
                while selected > list_idx+1:
                    self.move_up(selected, keep_index=True)
                    selected -= 1
                self.selectV.set(selected)
                self.show_selected()

    def move_down_selected_to_next_free(self):
        selected = self.selectV.get()
        if 0 <= selected < len(self.e2s_samples):
            res = self.get_next_free_index(1, self.e2s_samples[selected].get_esli().OSC_0index)
            if res:
                list_idx, osc_idx = res
                esli = self.e2s_samples[selected].get_esli()
                esli.OSC_0index = esli.OSC_0index1 = osc_idx
                self.update_sample(selected)
                while selected < list_idx-1:
                    self.move_down(selected, keep_index=True)
                    selected += 1
                self.selectV.set(selected)
                self.show_selected()

    def play(self, e2s_sample):
        riff_fmt = e2s_sample.get_fmt()
        audio.player.play_start(audio.Sound(e2s_sample.get_data().rawdata,riff_fmt))

    def play_stop(self):
        audio.player.play_stop()

    def edit(self, smpl_num):
        if not self.sliceEditDialog:
            self.sliceEditDialog = SliceEditorDialog(self.parent)
        self.sliceEditDialog.sliceEditor.set_sample(self, smpl_num)
        self.sliceEditDialog.run()

    def export(self, e2s_sample):
        oscNum=e2s_sample.get_esli().OSC_0index+1
        oscName=e2s_sample.get_esli().OSC_name.decode('ascii', 'ignore').split('\x00')[0]
        filename = tk.filedialog.asksaveasfilename(parent=self.parent,title="Export sample as",defaultextension='.wav',filetypes=(('Wav Files','*.wav'), ('All Files','*.*'))
                                                    ,initialfile="{:0>3}_{}.wav".format(oscNum,oscName))
        if filename:
            try:
                with open(filename, 'wb') as f:
                    e2s_sample.write(f, export_smpl=self.parent.export_opts.export_smpl, export_cue=self.parent.export_opts.export_cue)
            except Exception as e:
                tk.messagebox.showwarning(
                "Export sample as",
                "Cannot save sample as:\n{}\nError message:\n{}".format(filename, e)
                )

class ToManySamples(Exception):
    """Exception raised when registering a new sample while e2sSample is full."""
    pass

class SampleAllEditor(tk.Tk):
    """
    TODO:
    - check box: import sample and keep original number
    - sort imported samples
    - check box: remove unhandled chunks
    - button: edit sample
    """

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        GUI.res.init()

        self.import_opts = ImportOptions()
        self.export_opts = ExportOptions()

        # Set the window title
        self.wm_title("Open e2sSample.all Library Editor")
        self.minsize(width=600,height=500)

        #self.frame = VerticalScrolledFrame(self)
        #self.frame.pack(fill=tk.BOTH, expand=tk.YES)
        #self.sampleList = SampleList(self.frame.interior)
        fr = tk.Frame(self,borderwidth=2, relief='sunken')
        self.sampleList = SampleList(self, fr, borderwidth=2)

        fr2 = tk.Frame(fr, borderwidth=2)

        tk.Frame(fr2).pack(fill=tk.Y, expand=True)

        self.exchangeButton = tk.Button(fr2, image=GUI.res.exchangeIcon, command=self.exchange)
        ToolTip(self.exchangeButton, follow_mouse=1, text="exchange with another")
        self.exchangeButton.pack(padx=2, pady=2)

        tk.Frame(fr2, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X,padx=2, pady=5)

        self.moveUp100Button = tk.Button(fr2, image=GUI.res.swap_prev100Icon, command=lambda: [self.sampleList.move_up_selected() for i in range(100) ])
        ToolTip(self.moveUp100Button, follow_mouse=1, text="swap up by 100")
        self.moveUp100Button.pack(padx=2, pady=2)

        self.moveUp10Button = tk.Button(fr2, image=GUI.res.swap_prev10Icon, command=lambda: [self.sampleList.move_up_selected() for i in range(10) ])
        ToolTip(self.moveUp10Button, follow_mouse=1, text="swap up by 10")
        self.moveUp10Button.pack(padx=2, pady=2)

        self.moveUpButton = tk.Button(fr2, image=GUI.res.swap_prevIcon, command=self.sampleList.move_up_selected)
        ToolTip(self.moveUpButton, follow_mouse=1, text="swap up")
        self.moveUpButton.pack(padx=2, pady=2)

        self.moveDownButton = tk.Button(fr2, image=GUI.res.swap_nextIcon, command=self.sampleList.move_down_selected)
        ToolTip(self.moveDownButton, follow_mouse=1, text="swap down")
        self.moveDownButton.pack(padx=2, pady=2)

        self.moveDown10Button = tk.Button(fr2, image=GUI.res.swap_next10Icon, command=lambda: [self.sampleList.move_down_selected() for i in range(10) ])
        ToolTip(self.moveDown10Button, follow_mouse=1, text="swap down by 10")
        self.moveDown10Button.pack(padx=2, pady=2)

        self.moveDown100Button = tk.Button(fr2, image=GUI.res.swap_next100Icon, command=lambda: [self.sampleList.move_down_selected() for i in range(100) ])
        ToolTip(self.moveDown100Button, follow_mouse=1, text="swap down by 100")
        self.moveDown100Button.pack(padx=2, pady=2)

        tk.Frame(fr2, height=2, bd=1, relief=tk.SUNKEN).pack(fill=tk.X,padx=2, pady=5)

        self.moveUpFreeButton = tk.Button(fr2, image=GUI.res.prev_freeIcon, command=self.sampleList.move_up_selected_to_next_free)
        ToolTip(self.moveUpFreeButton, follow_mouse=1, text="move up to next free")
        self.moveUpFreeButton.pack(padx=2, pady=2)
        self.moveDownFreeButton = tk.Button(fr2, image=GUI.res.next_freeIcon, command=self.sampleList.move_down_selected_to_next_free)
        ToolTip(self.moveDownFreeButton, follow_mouse=1, text="move down to next free")
        self.moveDownFreeButton.pack(padx=2, pady=2)

        tk.Frame(fr2).pack(fill=tk.Y, expand=True)

        fr2.pack(side=tk.LEFT, fill=tk.Y)

        self.sampleList.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.YES)
        fr.pack(fill=tk.BOTH, expand=tk.YES)

        fr = tk.Frame(self,borderwidth=2, relief='sunken')
        tk.Label(fr,text='/ '+str(e2s.WAVDataMaxSize)).pack(side=tk.RIGHT)
        self.sizeEntry = MaxValueEntry(fr, e2s.WAVDataMaxSize, width=8, textvariable=self.sampleList.WAVDataSize, state=tk.DISABLED, justify=tk.RIGHT)
        self.sizeEntry.pack(side=tk.RIGHT)
        tk.Label(fr,text='Total Data Size : ').pack(side=tk.RIGHT)

        self.buttonDonateEur = tk.Button(fr, command=self.donate_eur, image=GUI.res.donateEurIcon)
        ToolTip(self.buttonDonateEur, follow_mouse=1, text="what about\noffering me a beer with € ?")
        self.buttonDonateEur.pack(side=tk.LEFT)
        self.buttonDonateUsd = tk.Button(fr, command=self.donate_usd, image=GUI.res.donateUsdIcon)
        ToolTip(self.buttonDonateUsd, follow_mouse=1, text="what about\noffering me a beer with $ ?")
        self.buttonDonateUsd.pack(side=tk.LEFT)

        self.buttonAbout=tk.Button(fr, text="About", width=10, command=self.about)
        tk.Frame(fr).pack(side=tk.TOP,fill=tk.Y,expand=1)
        self.buttonAbout.pack(side=tk.TOP)
        tk.Frame(fr).pack(side=tk.TOP,fill=tk.Y,expand=1)
        fr.pack(side=tk.BOTTOM,fill=tk.X)

        fr = tk.Frame(self)
        fr2 = tk.Frame(fr, borderwidth=2)
        self.buttonImport = tk.Button(fr2, text="Import wav Sample(s)", command=self.import_sample)
        self.buttonImport.pack(side=tk.TOP, fill=tk.BOTH)

        self.buttonImportE2s = tk.Button(fr2, text="Import e2sSample.all", command=self.import_all_sample)
        self.buttonImportE2s.pack(side=tk.TOP, fill=tk.BOTH)
        fr2.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        fr2 = tk.Frame(fr, borderwidth=2)
        self.buttonImportOptions = tk.Button(fr2, text="Import Options", width=15, command=self.import_options)
        self.buttonImportOptions.pack(fill=None,padx=5)
        fr2.pack(side=tk.LEFT, fill=None)
        fr.pack(side=tk.TOP, fill=tk.BOTH)

        fr = tk.Frame(self)
        fr2 = tk.Frame(fr, borderwidth=2)
        self.buttonExpAll = tk.Button(fr2, text="Export all as wav", command=self.export_all_sample)
        self.buttonExpAll.pack(side=tk.TOP, fill=tk.BOTH)
        fr2.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        fr2 = tk.Frame(fr, borderwidth=2)
        self.buttonExportOptions = tk.Button(fr2, text="Export Options", width=15, command=self.export_options)
        self.buttonExportOptions.pack(fill=None, padx=5)
        fr2.pack(side=tk.LEFT, fill=None)
        fr.pack(side=tk.TOP, fill=tk.BOTH)

        self.buttonLoad = tk.Button(self, text="Open", width=10, command=self.load)
        self.buttonLoad.pack(side=tk.LEFT,fill=tk.Y,padx=5,pady=5)

        self.buttonClear = tk.Button(self, text="Clear all", width=10, command=self.clear)
        self.buttonClear.pack(side=tk.RIGHT,padx=5,pady=5)

        self.buttonSaveAs = tk.Button(self, text="Save As", width=10, command=self.save_as)
        self.buttonSaveAs.pack(side=tk.TOP,fill=tk.Y,padx=5,pady=5)

        self.restore_binding()

        self.update_idletasks()
        width, height = (self.winfo_width(), self.winfo_height())
        self.minsize(width, height)

    def exchange(self):
        sl = self.sampleList
        selected = sl.get_selected()
        if selected is not None:
            s_num = sl.e2s_samples[selected].get_esli().OSC_0index+1;
            s_name = sl.e2s_samples[selected].get_esli().OSC_name.decode('ascii', 'ignore').split('\x00')[0];
            exchg_with = [
                (sl.e2s_samples[i].get_esli().OSC_0index+1,
                 sl.e2s_samples[i].get_esli().OSC_name.decode('ascii', 'ignore').split('\x00')[0]) for i in range(len(sl.e2s_samples))
                ]
            dialog = ExchangeSampleDialog(self, (s_num, s_name), exchg_with)
            self.wait_window(dialog)
            if dialog.result is not None and dialog.result >= 0 and dialog.result != selected:
                sl.exchange(selected, dialog.result)
                sl.set_selected(dialog.result)

    def donate_eur(self):
        webbrowser.open('https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=L6BSNDEHYQ2HE')
    
    def donate_usd(self):
        webbrowser.open('https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=PG6YDQS4EZAE2')

    def about(self):
        about = AboutDialog(self)

    def clear(self):    
        wd = WaitDialog(self)
        wd.run(self.sampleList.clear)

    def import_options(self):
        dialog = ImportOptionsDialog(self, self.import_opts)
        self.wait_window(dialog)

    def export_options(self):
        dialog = ExportOptionsDialog(self, self.export_opts)
        self.wait_window(dialog)

    def load(self):
        filename = tk.filedialog.askopenfilename(parent=self,title="Select e2s Sample.all file to open",filetypes=(('.all Files','*.all'),('All Files','*.*')))
        if filename:
            def fct():
                try:
                    samplesAll = e2s.e2s_sample_all(filename=filename)
                except Exception as e:
                    tk.messagebox.showwarning(
                    "Open",
                    "Cannot use this file:\n{}\nError message:\n{}".format(filename, e)
                    )
                    return

                if samplesAll._loadErrors:
                    tk.messagebox.showwarning(
                    "Open",
                    ("Recovered from {} error(s) in this file:\n{}\n"
                     "The file is probably corrupted or you found a bug.\n"
                     "See log file for details."
                    )
                    .format(samplesAll._loadErrors, filename)
                    )
                
                self.sampleList.clear()
                for sample in samplesAll.samples:
                    self.sampleList.add_new(sample)
                    if len(self.sampleList.samples) == 1:
                        self.update_idletasks()
                        width, height = (self.winfo_reqwidth(), self.winfo_reqheight())
                        self.minsize(width, height)
            wd = WaitDialog(self)
            wd.run(fct)
                
    def save_as(self):
        if not self.sampleList.WAVDataSize.get() > e2s.WAVDataMaxSize or tk.messagebox.askyesno("Memory overflow", "Are you sure to save with memory overflow?"):
            filename = tk.filedialog.asksaveasfilename(parent=self,title="Save as e2s Sample.all file",defaultextension='.all',filetypes=(('.all Files','*.all'),('All Files','*.*')),initialfile='e2sSample.all')
            if filename:
                def fct():
                    sampleAll = e2s.e2s_sample_all()
                    for e2s_sample in self.sampleList.e2s_samples:
                        sampleAll.samples.append(e2s_sample)
                    try:
                        sampleAll.save(filename)
                    except Exception as e:
                        tk.messagebox.showwarning(
                        "Save as",
                        "Cannot save to this file:\n{}\nError message:\n{}".format(filename, e)
                        )
                wd = WaitDialog(self)
                wd.run(fct)

    def _import_sample_helper(self, filename):
        try:
            return e2s_sample_import.from_wav(filename, self.import_opts)

        except e2s_sample_import.NotWaveFormatPcm:
            tk.messagebox.showwarning(
            "Import WAV",
            "Cannot use this file:\n{}\nWAV format must be WAVE_FORMAT_PCM".format(filename)
            )

        except e2s_sample_import.EmptyWav:
            tk.messagebox.showwarning(
            "Import WAV",
            "Cannot use this file:\n{}\nNo data: empty samples are not allowed".format(filename)
            )

        except e2s_sample_import.NotSupportedBitPerSample:
            tk.messagebox.showwarning(
            "Import WAV",
            "Cannot use this file:\n{}\nWAV format must preferably use 16 bits per sample.\n" +
            "8 bits and old 24 bits per sample are also supported but will be converted to 16 bits.\n"
            "Convert your file before importing it.".format(filename)
            )

        except BaseException as e:
            tk.messagebox.showwarning(
            "Import WAV",
            "Cannot use this file:\n{}\n"
            "The file is probably corrupted or you found a bug.\n"
            "See log file for details.\n"
            "Error message:\{}.".format(filename, e)
            )
            # also report it in log file
            print(e)


    def import_sample(self):
        filenames = tk.filedialog.askopenfilenames(parent=self,title="Select WAV file(s) to import",filetypes=(('Wav Files','*.wav'), ('All Files','*.*')))
        def fct():
            num_converted = dict()
            for filename in filenames:
                res = self._import_sample_helper(filename)

                if not res:
                    continue

                sample, converted_from, converted_to_mono = res

                if converted_from:
                    num_converted[converted_from] = num_converted.get(converted_from, 0) + 1
                if converted_to_mono:
                    num_converted['mono'] = num_converted.get('mono', 0) + 1
                try:
                    self.register_new_sample(sample)
                except ToManySamples:
                    tk.messagebox.showwarning(
                    "Import WAV",
                    "Cannot use this file:\n{}\nToo many samples.".format(filename)
                    )
                    break


            if num_converted:
                tk.messagebox.showinfo(
                    "Import WAV",
                    ("{} file(s) converted to mono.\n".format(num_converted['mono']) if num_converted.get('mono') else "") +
                    ("{} file(s) converted from 8 bits to 16 bits.\n".format(num_converted[8]) if num_converted.get(8) else "") +
                    ("{} file(s) converted from 24 bits to 16 bits.\n".format(num_converted[24]) if num_converted.get(24) else "")
                    )

        wd = WaitDialog(self)
        wd.run(fct)
                
    def import_all_sample(self):
        filename = tk.filedialog.askopenfilename(parent=self,title="Select e2sSample.all file to import",filetypes=(('.all Files','*.all'),('All Files','*.*')))
        if filename:        
            def fct():
                try:
                    samplesAll = e2s.e2s_sample_all(filename=filename)
                except Exception as e:
                    tk.messagebox.showwarning(
                    "Import e2sSample.all",
                    "Cannot use this file:\n{}\nError message:\n{}".format(filename, e)
                    )
                    return
                if samplesAll._loadErrors:
                    tk.messagebox.showwarning(
                    "Import e2sSample.all",
                    ("Recovered from {} error(s) in this file:\n{}\n"
                     "The file is probably corrupted or you found a bug.\n"
                     "See log file for details."
                    )
                    .format(samplesAll._loadErrors, filename)
                    )
                
                for sample in samplesAll.samples:
                    e2s_sample_import.apply_forced_options(sample, self.import_opts)
                    try:
                        self.register_new_sample(sample)
                    except ToManySamples:
                        tk.messagebox.showwarning(
                        "Import e2sSample.all",
                        "Too many samples."
                        )
                        break

            wd = WaitDialog(self)
            wd.run(fct)

    def export_all_sample(self):
        if self.sampleList.samples:
            directory = tk.filedialog.askdirectory(parent=self,title="Export all samples to directory",mustexist=True)
            def fct():
                if directory:
                    # check files do not exist
                    for e2s_sample in self.sampleList.e2s_samples:
                        oscNum = e2s_sample.get_esli().OSC_0index+1
                        oscName = e2s_sample.get_esli().OSC_name.decode('ascii', 'ignore').split('\x00')[0]
                        filename = "{:0>3}_{}.wav".format(oscNum,oscName)
                        filename = filename.replace('/','-').replace('\\','-')
                        filename = directory+"/"+filename
                        # TODO: dialog to ask if replace/replace-all or select new rename
                        if os.path.exists(filename):
                            filename = tk.filedialog.asksaveasfilename(parent=self,title="File exists, export sample as [cancel to abort]",defaultextension='.wav',filetypes=(('Wav Files','*.wav'), ('All Files','*.*'))
                                                                      ,initialdir=directory,initialfile="{:0>3}_{}.wav".format(oscNum,oscName))
                            if not filename:
                                break
                        ok = False
                        while not ok:
                            try:
                                with open(filename, 'wb') as f:
                                    e2s_sample.write(f, export_smpl=self.export_opts.export_smpl, export_cue=self.export_opts.export_cue)
                            except Exception as e:
                                tk.messagebox.showwarning(
                                "Export sample as",
                                "Cannot save sample as:\n{}\nError message:\n{}".format(filename, e)
                                )
                                filename = tk.filedialog.asksaveasfilename(parent=self,title="Export sample as [cancel to abort]",defaultextension='.wav',filetypes=(('Wav Files','*.wav'), ('All Files','*.*'))
                                                                          ,initialdir=directory,initialfile="{:0>3}_{}.wav".format(oscNum,oscName))
                                if not filename:
                                    break
                            ok = True
                        if not ok:
                            break
                                
            wd = WaitDialog(self)
            wd.run(fct)

    def register_new_sample(self, e2s_sample):
        esli = e2s_sample.get_esli()

        nextsampleIndex = self.sampleList.get_next_free_sample_index(self.import_opts.smp_num_from-1)
        if nextsampleIndex is not None:
            esli.OSC_0index = esli.OSC_0index1 = nextsampleIndex

            self.sampleList.add_new(e2s_sample)
            if len(self.sampleList.samples) == 1:
                self.update_idletasks()
                width, height = (self.winfo_reqwidth(), self.winfo_reqheight())
                self.minsize(width, height)
        else:
            raise ToManySamples

    system = platform.system()

    def restore_binding(self):
        if self.system == 'Windows':
            def _on_mousewheel(event):
                self.sampleList.scroll(-1*(event.delta//120))
                return "break"
            self.bind('<MouseWheel>', _on_mousewheel)
            # TODO: add an option to select behaviour
            # do not scroll the interface if mouse is on a ttk Combobox
            #self.bind_class('TCombobox', '<MouseWheel>', lambda e: "break", "+")
            ## do not change ttk Combobox content on mouse wheel event
            self.bind_class('TCombobox', '<MouseWheel>', lambda e: None)
        elif self.system == 'Darwin':
            def _on_mousewheel(event):
                self.sampleList.scroll(-1*(event.delta))
            self.bind('<MouseWheel>', _on_mousewheel)
            #self.bind_class('TCombobox', '<MouseWheel>', lambda e: "break", "+")
            self.bind_class('TCombobox', '<MouseWheel>', lambda e: None)
        else:
            def _on_up(event):
                self.sampleList.scroll(-1)
            def _on_down(event):
                self.sampleList.scroll(1)
            self.bind('<Button-4>', _on_up)
            self.bind('<Button-5>', _on_down)
            #self.bind_class('TCombobox', '<Button-4>', lambda e: "break", "+")
            #self.bind_class('TCombobox', '<Button-5>', lambda e: "break", "+")
            self.bind_class('TCombobox', '<Button-4>', lambda e: None)
            self.bind_class('TCombobox', '<Button-5>', lambda e: None)


if __name__ == '__main__':
    # redirect outputs to a logger
    with logger() as log:
        # Create a window
        app = SampleAllEditor()
        app.mainloop()
        audio.terminate()
