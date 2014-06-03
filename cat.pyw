#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This is a main unit of Uzhgorod geo catalog program
# Dependences: wx, matplotlib, numpy

import wx
import wx.xrc as xrc
wx = wx  # just the trick :)
import os
import sqlite3

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
            self.notebook = xrc.XRCCTRL(self.frame, "Notebook")
            self.load_bt = xrc.XRCCTRL(self.panel, "button_1")
            self.list_ctrl = xrc.XRCCTRL(self.frame, "list_ctrl_1")

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
            # self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
            self.frame.Bind(wx.EVT_LISTBOX, self.show_el, id=xrc.XRCID('list_box_1'))
            self.frame.Bind(wx.EVT_BUTTON, self.load_res, id=xrc.XRCID('button_1'))
            # self.frame.Bind(wx.EVT_CHECKBOX, self.On_m0_ch, id=xrc.XRCID('checkbox_1'))
            self.Bind(wx.EVT_BUTTON, self.OnAdd, id=xrc.XRCID("button_2"))
            # self.Bind(wx.EVT_KEY_DOWN, self.OnKeyLb, id=xrc.XRCID('lb_nps'))
            #self.Bind(wx.EVT_CHAR, self.OnKeyFrame)
            ######
            # self.frame.Size = (500, 400)
            self.frame.Show()
            # global self_path
            # self_path = os.path.dirname(os.path.abspath(__file__))
            wx.CallAfter(self.list_box.SetFocus)
        else:
            print "File cat_gui.xrc don't find"
        return True

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

    def OnAdd(self, evt):
        sel = self.list_box.GetSelections()
        # print sel, len(sel)
        if sel:
            sel = sel[0]
        s_id = self.list_box.GetItems()[sel]
        if s_id[-1] != '+':
            res_c.execute("""CREATE TABLE if not exists '%s' (satid INTEGER, date DATE, time TIME UNIQUE, RA FLOAT, DEC FLOAT, m FLOAT)""" % s_id)
            global res
            coo = res[sel].coord
            for c in coo:
                res_c.execute("""insert or ignore into '%s' values (%s,%f,%f,%f,%f,%f)""" % (s_id, s_id, c.date, c.time, c.RA, c.DEC, c.m))
            res_conn.commit()
            print s_id, "Added to DB"
            self.list_box.SetString(sel, s_id + "+")

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