#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This is a main unit of Uzhgorod geo catalog program
# Dependences: wx, matplotlib, numpy

import wx
import wx.xrc as xrc
wx = wx  # just the trick :)
import os
import sqlite3
import matplotlib
matplotlib.use('WXAgg')
import matplotlib.figure as figure
import matplotlib.backends.backend_wxagg as wxagg
import numpy as np

res = []
check, check_match = [], []


res_conn = sqlite3.connect("cat_res.db")
res_c = res_conn.cursor()
print 'Connecting to RES database ...'

el_conn = sqlite3.connect("cat_elemants.db")
el_c = el_conn.cursor()
print 'Connecting to ELEMENTS database ...'


def warn(parent, message, caption='Warning!'):
    dlg = wx.MessageDialog(parent, message, caption, wx.OK | wx.ICON_WARNING)
    dlg.ShowModal()
    dlg.Destroy()


class MyApp(wx.App):
    def OnInit(self):
        if os.path.exists("cat_gui.xrc"):
            self.res = xrc.XmlResource("cat_gui.xrc")
            self.frame = self.res.LoadFrame(None, 'frame_1')

            self.panel = xrc.XRCCTRL(self.frame, "panel_1")
            # self.panel2 = xrc.XRCCTRL(self.frame, "panel_2")
            self.statusbar = xrc.XRCCTRL(self.frame, "frame_1_statusbar")
            self.statusbar.SetStatusText('FileName=', 0)

            self.list_box = xrc.XRCCTRL(self.frame, "list_box_1")
            self.notebook = xrc.XRCCTRL(self.frame, "notebook_1")
            self.load_bt = xrc.XRCCTRL(self.panel, "button_1")
            self.list_ctrl = xrc.XRCCTRL(self.frame, "list_ctrl_1")
            self.combo_box = xrc.XRCCTRL(self.frame, "combo_box_1")
            self.radio_box = xrc.XRCCTRL(self.frame, "radio_box_1")

            self.list_ctrl.InsertColumn(0, '', width=50)
            self.list_ctrl.InsertColumn(1, 'Elements measured', width=150)
            self.list_ctrl.InsertColumn(2, 'Elements matched', width=150)
            # self.list_ctrl.InsertColumn(2, 'Sim Script', width=80)
            # self.list_ctrl.Append(1,1)
            self.list_ctrl.InsertStringItem(0, "sat_id")
            self.list_ctrl.InsertStringItem(1, "a")
            self.list_ctrl.InsertStringItem(2, "e")
            self.list_ctrl.InsertStringItem(3, "i")
            self.list_ctrl.InsertStringItem(4, "W")
            self.list_ctrl.InsertStringItem(5, "w")
            self.list_ctrl.InsertStringItem(6, "M")
            self.list_ctrl.InsertStringItem(7, "Lon")

            ####Binds
            TopParent = self.GetTopWindow()
            TopParent.Bind(wx.EVT_CLOSE, self.OnDestroy)
            self.frame.Bind(wx.EVT_LISTBOX, self.show_el, id=xrc.XRCID('list_box_1'))
            self.frame.Bind(wx.EVT_BUTTON, self.load_res, id=xrc.XRCID('button_1'))
            self.frame.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.load_db, id=xrc.XRCID("notebook_1"))
            # self.frame.Bind(wx.EVT_CHECKBOX, self.On_m0_ch, id=xrc.XRCID('checkbox_1'))
            self.Bind(wx.EVT_BUTTON, self.OnAdd, id=xrc.XRCID("button_2"))
            # self.Bind(wx.EVT_COMBOBOX, self.select_sat, id=xrc.XRCID("combo_box_1"))
            self.Bind(wx.EVT_RADIOBOX, self.draw_element, id=xrc.XRCID("radio_box_1"))

            # self.Bind(wx.EVT_KEY_DOWN, self.OnKeyLb, id=xrc.XRCID('lb_nps'))
            # self.Bind(wx.EVT_CHAR, self.OnKeyFrame)
            ######
            # self.frame.Size = (500, 400)
            self.frame.Show()
            # global self_path
            # self_path = os.path.dirname(os.path.abspath(__file__))
            wx.CallAfter(self.list_box.SetFocus)
            self.create_main_panel()
        else:
            print "File cat_gui.xrc don't find"
        return True

    def create_main_panel(self):
        """ Creates the main panel with all the controls on it:
             * mpl canvas
             * mpl navigation toolbar
             * Control panel for interaction
        """
        self.panel3 = xrc.XRCCTRL(self.frame, "panel_3")
        # Create the mpl Figure and FigCanvas objects.
        # 5x3 inches, 100 dots-per-inch
        #
        self.dpi = 100
        self.fig = figure.Figure((5.0, 3.0), dpi=self.dpi)
        self.canvas = wxagg.FigureCanvasWxAgg(self.panel3, -1, self.fig)
        self.axes = self.fig.add_subplot(111)
        # Create the navigation toolbar, tied to the canvas
        self.toolbar = wxagg.NavigationToolbar2WxAgg(self.canvas)
        #
        # Layout with box sizers
        #
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.vbox.Add(self.canvas, 1, wx.LEFT | wx.TOP | wx.GROW)
        # self.vbox.AddSpacer(25)
        self.vbox.Add(self.toolbar, 0, wx.EXPAND)

        self.panel3.SetSizer(self.vbox)
        self.vbox.Fit(self.panel3)

    def load_res(self, evt):
        from coord import read_res, read_check
        self.list_box.Set("")
        wildcard = "RES(*.res)|*.res;*.RES"
        dlg = wx.FileDialog(self.frame, message="Choose File", defaultDir=os.getcwd(),
                            defaultFile='', wildcard=wildcard, style=wx.OPEN | wx.CHANGE_DIR)
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
            global res, check, check_match
            for path in paths:
                try:
                    res = read_res(path)
                    for sat in res:
                        self.list_box.Append(str(sat.ser_id))
                    check, check_match = read_check(path + ".check")
                    # print res[1].ser_id, check_match[1].sat_ID, check[1].a, check_match[1].a
                except:
                    warn(self.frame, "Wrong file format probably")
            self.statusbar.SetStatusText('FileName=' + os.path.basename(path), 0)
        dlg.Destroy()

    def show_el(self, evt):
        sel = self.list_box.GetSelections()
        # print sel, len(sel)
        if sel:
            sel = sel[0]
        # print "graph", self.list_box.GetItems()[sel]
        global check, check_match
        if check:
            for el in check:
                if el.sat_ID == self.list_box.GetItems()[sel]:
                    self.list_ctrl.SetStringItem(0, 1, el.sat_ID)
                    self.list_ctrl.SetStringItem(1, 1, '%.7f' % el.a)
                    self.list_ctrl.SetStringItem(2, 1, '%.10f' % el.e)
                    self.list_ctrl.SetStringItem(3, 1, '%.10f' % el.i)
                    self.list_ctrl.SetStringItem(4, 1, '%.10f' % el.W)
                    self.list_ctrl.SetStringItem(5, 1, '%.10f' % el.w)
                    self.list_ctrl.SetStringItem(6, 1, '%.10f' % el.M)
                    self.list_ctrl.SetStringItem(7, 1, '%.2f' % el.Lon)
                    elm = check_match[check.index(el)]  # matched elements
                    self.list_ctrl.SetStringItem(0, 2, elm.sat_ID)
                    self.list_ctrl.SetStringItem(1, 2, '%.7f' % elm.a)
                    self.list_ctrl.SetStringItem(2, 2, '%.10f' % elm.e)
                    self.list_ctrl.SetStringItem(3, 2, '%.10f' % elm.i)
                    self.list_ctrl.SetStringItem(4, 2, '%.10f' % elm.W)
                    self.list_ctrl.SetStringItem(5, 2, '%.10f' % elm.w)
                    self.list_ctrl.SetStringItem(6, 2, '%.10f' % elm.M)

    def load_db(self, evt):
        if self.notebook.GetSelection() == 1:  # View page
            print "Read elements db..."
            sat_list = el_conn.execute("SELECT name FROM sqlite_master WHERE type='table' ").fetchall()
            sl = []
            for t in sat_list:
                sl.append(t[0])
            self.combo_box.Clear()
            self.combo_box.AppendItems(sl)
            self.combo_box.SetSelection(0)

    def OnAdd(self, evt):
        sel = self.list_box.GetSelections()
        # print sel, len(sel)
        if sel:
            sel = sel[0]
        s_id = self.list_box.GetItems()[sel]
        if s_id[-1] != '+':
            res_c.execute("""CREATE TABLE if not exists '%s' (satid INTEGER, date INTEGER, time FLOAT UNIQUE, RA FLOAT, DEC FLOAT, m FLOAT)""" % s_id)
            el_c.execute("""CREATE TABLE if not exists '%s' (satid INTEGER, date INTEGER, time1 FLOAT UNIQUE, time2 FLOAT, a FLOAT, e FLOAT, i FLOAT, W FLOAT, we FLOAT, M FLOAT, Lon FLOAT)""" % s_id)
            global res, check, check_match
            coo = res[sel].coord
            for c in coo:
                res_c.execute("""insert or ignore into '%s' values (%s,%i,%f,%f,%f,%f)"""
                              % (s_id, s_id, c.date, c.time, c.RA, c.DEC, c.m))
            for el in check:
                if el.sat_ID == self.list_box.GetItems()[sel]:
                    el_c.execute("""insert or ignore into '%s' values (%s,%i,%f,%f,%f,%f,%f,%f,%f,%f,%f)"""
                                 % (el.sat_ID, el.sat_ID, coo[0].date, coo[0].time, coo[-1].time, el.a, el.e, el.i, el.W, el.w, el.M, el.Lon))
            res_conn.commit()
            el_conn.commit()
            print s_id, "Added to DB"
            self.list_box.SetString(sel, s_id + "+")

    def draw_element(self, evt):
        n_e = self.radio_box.GetSelection()
        n_s = self.combo_box.GetSelection()
        print "Graph " + self.radio_box.GetString(n_e) + " for " + self.combo_box.GetString(n_s)
        """ Redraws the figure"""
        # clear the axes and redraw the plot anew
        #
        self.axes.clear()
        x, y = np.random.random((10, 2)).T
        self.axes.scatter(x, y)
        self.canvas.draw()

    def OnDestroy(self, event):
        ## clean up resources as needed here
        # event.Skip()
        print "Close database..."
        res_conn.close()
        el_conn.close()
        self.Exit()

if __name__ == "__main__":
    app = MyApp(False)
    app.MainLoop()